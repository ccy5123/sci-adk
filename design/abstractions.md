# sci-adk Core Abstractions

> Status: v0.1 CONFIRMED — first-session deliverable (2026-05-26).
> Three structural decisions resolved; see "Resolved decisions".
> Provisional location under `design/`; to be reconciled when the directory
> structure is decided. Language-neutral schema; implementation language TBD.

sci-adk is a **research compiler**: it consumes a four-pane research proposal
and emits a paper draft + working code + an evidence trail. The three types
below are the system core. Everything downstream (loop, agents, renderers)
operates on them.

---

## Organizing principle: record vs belief

The deepest software assumption that breaks for science (see
`recon/sw-assumptions.md` A4/A9/A13/A17, `recon/tdd-mismatch.md` Q2a/Q2b) is
that *build state equals truth* — a single monotone, binary, terminal signal.
Science separates two things the SW model conflates:

- **The record of what happened** is monotone and append-only. You never
  unmake an experiment. Null and negative results are part of the record.
  → **Evidence** is an immutable, append-only log.

- **What we currently believe** is non-monotone and revisable. New evidence
  raises or lowers confidence; a once-supported claim can be demoted or
  retracted. This is normal science, not a defect.
  → **Claim** is a mutable belief state *derived from* Evidence.

**Spec** is the third type: the frozen pre-registration contract. It fixes the
*question* and the *evaluation rule* before results are seen (the valid kernel
of RED-first / pre-registration) — without fixing the *answer*.

```
  Spec  ──(frozen question + decision rules)──┐
        │                                       │
        ▼                                       ▼
   [ loop: hypothesis → experiment ]      evaluate against
        │                                  decision_rules
        ▼                                       │
   Evidence (append-only) ───────────────► Claim (revisable)
        ▲                                       │
        └────────── new evidence demotes ───────┘
                                                 │
                                                 ▼
                                     paper + code + evidence trail
```

---

## Identifiers and shared notes

- `Id` is an opaque stable identifier (string). Cross-type references use ids.
- All timestamps are ISO-8601 UTC.
- `?` suffix = optional. `[]` = ordered list. `{}` = set. `|` = sum/enum.
- Field names are normative (they become code); prose is explanatory.
- Notation is descriptive, not tied to any language's type system.

---

## 1. Spec — compiler input (frozen pre-registration contract)

Represents a four-pane proposal as a compiled, evaluable contract. Frozen once
accepted: the question and decision rules do not change mid-run (anti-HARKing).
Amendments are allowed but recorded as new versions, never silent edits.

```
Spec {
  id            : Id
  created_at    : Timestamp
  version       : int                  // bumped on amendment; prior versions retained
  raw_proposal  : RawProposal          // provenance: what the user actually asked
  hypotheses    : Hypothesis[]          // derived from the "goal" pane
  method        : MethodPlan            // derived from the "method" pane
  target_claims : TargetClaim[]         // derived from the "expected output" pane
}

RawProposal {                          // the literal four-pane input, verbatim
  background      : text
  goal            : text
  method          : text
  expected_output : text
}

Hypothesis {
  id            : Id
  statement     : text                 // e.g. "molecule graphs admit a bijective Gödel-style encoding"
  mode          : confirmatory | exploratory   // honest pre-declaration (recon Q2c gap 2)
  decision_rule : DecisionRule         // what counts as support/refutation
}

DecisionRule {                         // NOT binary acceptance; a rule over continuous evidence
  kind      : threshold | bayesian | interval | proof | qualitative
  // examples by kind:
  //   bayesian   -> "posterior odds > 10 => support"
  //   interval   -> "effect-size 95% CI excludes 0 => support; includes 0 => null"
  //   proof      -> "a verified derivation exists => support; a counterexample => refute"
  //   qualitative-> "expert/structured criterion stated in prose"
  expression : text                    // human-readable rule
  params     : map<string, value>?     // machine-usable thresholds where applicable
}

MethodPlan {
  approaches : text[]                  // techniques/tools intended (informs the loop, not binding)
  tools      : ToolRef[]?              // solvers/languages/datasets expected (recon N5)
}

TargetClaim {                          // a contribution the user hopes to establish
  id              : Id
  statement       : text
  answers         : Id                 // hypothesis id this target is about
}
```

**Invariants**

- S1. A frozen `Spec` version is immutable. Changes create `version+1` with a
  recorded rationale; old versions remain reachable.
- S2. Every `Hypothesis` has exactly one `mode` and one `DecisionRule`.
- S3. `DecisionRule` MUST express how *continuous/uncertain* evidence maps to
  support/refute/null. A purely binary pass/fail rule is a smell, not invalid,
  but must be justified.
- S4. `TargetClaim.answers` references an existing `Hypothesis.id`.
- S5. **Amending a frozen Spec (`version+1`) requires a human checkpoint, even
  in fully autonomous mode.** This is the single carve-out from autonomy:
  self-amending pre-registration would void the anti-HARKing guarantee that
  separates sci-adk from a result-fitting tool. (Decided 2026-05-26.)

---

## 2. Evidence — accumulated record (immutable, append-only)

The audit trail. Each item records one attempt and its result, with full
provenance, and which hypothesis/claim it bears on. The log only grows.

```
EvidenceItem {
  id          : Id
  created_at  : Timestamp
  spec_id     : Id                     // which Spec this run serves
  kind        : experiment_run | proof_step | literature | counterexample | observation
  provenance  : Provenance             // reproducibility (recon RA1/RA2/N7)
  result      : Result                 // typed; may be continuous/probabilistic OR qualitative
  bears_on    : Bearing[]              // which hypotheses/claims, and in what direction
}

Provenance {
  code_ref    : text?                  // commit / worktree / script path + line
  data_ref    : text?                  // dataset id + version
  seed        : int?                   // RNG seed (stochastic reproducibility)
  environment : text?                  // toolchain / container / lib versions
  cost        : Cost?                  // tokens / wallclock (recon RA2 telemetry)
}

Result {
  type   : quantitative | qualitative
  // quantitative payload (any subset, as the method produces):
  point        : number?               // estimate / statistic
  effect_size  : number?
  ci           : [number, number]?     // confidence/credible interval
  p_value      : number?
  posterior    : number?               // or a reference to a posterior artifact
  residual     : number?
  predictive_error : number?
  // qualitative payload:
  finding      : text?                 // literature claim, proof step, counterexample, note
  artifact_ref : text?                 // figure/table/file produced
}

Bearing {
  target_id : Id                       // a Hypothesis id or a Claim id
  direction : supports | refutes | neutral | inconclusive   // all first-class (recon A13)
  weight    : number?                  // optional strength of this bearing
}
```

**Invariants**

- E1. Append-only. An `EvidenceItem` is never mutated or deleted after
  creation. Corrections are *new* items that reference the superseded one.
- E2. `direction = refutes | inconclusive | neutral` is a valid, complete
  outcome. A null result is recorded, never treated as "stuck" or failure.
- E3. Every `EvidenceItem` carries enough `Provenance` to attempt
  reproduction, or explicitly marks what is missing.
- E4. `bears_on.target_id` references an existing Hypothesis or Claim.

---

## 3. Claim — compiler output (revisable belief)

A contribution-level statement with uncertainty, derived from Evidence. This is
what becomes the paper's claims. Not a binary DONE; a position that can move as
evidence accumulates.

```
Claim {
  id                : Id
  spec_id           : Id
  answers           : Id                // hypothesis id this claim addresses
  statement         : text
  status            : ClaimStatus       // NON-monotone (recon A9/A17)
  confidence        : Confidence        // continuous or graded, not binary
  evidence_set      : EvidenceLink[]    // supporting AND refuting evidence
  scope_limitations : text              // "Research Limitations" (recon domain-research M3)
  mode              : confirmatory | exploratory   // inherited from Hypothesis; honest label
  renders_to        : RenderTarget?     // paper section / deliverable mapping
  history           : StatusChange[]    // audit of belief movement
}

ClaimStatus = proposed
            | supported
            | contested      // mixed evidence; support and refutation coexist
            | refuted
            | retracted      // withdrawn (e.g. provenance broken, reproduction failed)

Confidence {
  type        : credence | posterior | graded
  value       : number?                // credence/posterior in [0,1]
  level       : strong | moderate | weak | none ?   // graded fallback
  basis       : text                   // justification (required, recon meta-rule #4)
}

EvidenceLink {
  evidence_id : Id
  role        : supporting | refuting
}

StatusChange {
  at          : Timestamp
  from        : ClaimStatus
  to          : ClaimStatus
  triggered_by: Id                     // evidence id that caused the move
  note        : text?
}
```

**Invariants**

- C1. `status` may move in any direction over time. A `supported` claim can
  become `contested` or `refuted` when new Evidence arrives — this is normal,
  not a regression to be prevented.
- C2. Every status change appends a `StatusChange` to `history` citing the
  triggering Evidence. The belief is non-monotone but its *history* is
  append-only (mirrors E1).
- C3. `confidence.basis` (natural-language justification) is the load-bearing
  field and is always required. `value`/`level` is whichever indicator is
  *representative for the field* (a posterior, a p-value, "proven", a graded
  level) — the type does not privilege one; the basis text carries the actual
  judgment (recon meta-rule #4; decided 2026-05-26).
- C4. A null result is expressible as a Claim: e.g. statement = "no evidence
  for effect X", status = supported, confidence over the *absence*. Absence of
  effect is a claim, not the absence of a claim.
- C5. `evidence_set` includes refuting links, not only supporting ones. A claim
  hides nothing about the evidence against it.
- C6. A claim derived from `exploratory` evidence is labeled `exploratory` and
  may not be presented as `confirmatory` (anti-HARKing).

---

## Cross-type object graph

```
Spec 1 ──< Hypothesis >── answered by ──< Claim
  │                                        │
  └── target_claims ─────────────────────► │
                                            │
EvidenceItem >── bears_on ──► Hypothesis / Claim
Claim        >── evidence_set ──► EvidenceItem   (supporting + refuting)
```

- A `Spec` owns hypotheses and target claims.
- `EvidenceItem`s reference hypotheses/claims they bear on (many-to-many).
- `Claim`s reference the evidence that moves them (many-to-many, both roles).
- The only monotone structures are the *logs*: the Evidence log and each
  Claim's `history`. Belief (`Claim.status`, `Claim.confidence`) is free to move.

---

## Mapping to the loop (recon RC1 / tdd-mismatch)

The reusable loop skeleton (controller + `FeedbackGenerator` + `DecisionEngine`
interfaces, phases relabeled `gather → model → evaluate → review`) operates on
these types:

- `FeedbackGenerator` produces **EvidenceItems** (scientific metrics), not
  go-test/lint counts.
- `DecisionEngine` evaluates **Claim confidence against Spec decision_rules**,
  not a binary 0-conjunction quality gate.
- "Convergence" is *not* "errors == 0". It is "decision rules met OR evidence
  budget exhausted OR human checkpoint" — and a null result is a valid
  convergence, not a stuck state.

---

## Deliberately left open (not under-specified by accident)

- **Implementation language / representation format** — decided with directory
  structure & milestone. Schema is language-neutral on purpose.
- **Confidence computation engine** — how `posterior`/`effect_size` are
  actually computed (recon N1). The *type* is fixed here; the *engine* is a
  later, separate component (recon flagged it as scratch work).
- **Renderer** — how Claims + Evidence become a paper draft. Out of scope for
  the core types; `renders_to` is the only hook.
- **Persistence** — how the Evidence log and Claims are stored/versioned
  (recon domain-database M, N7). Append-only is a requirement; the store is TBD.

---

## No hardcoded metrics (tool policy)

Per the project tool policy, **no success metric is hardcoded** anywhere
(no 85% coverage, no fixed threshold). The replacement for the excluded SW
metrics (LSP pass, coverage, conventional-commit "done") is structural, not a
new constant: **each `Spec` declares its own `DecisionRule` per hypothesis**,
and `Claim.confidence` is judged against *that* rule. The types here are the
mechanism that lets metrics be per-research rather than global.

## Resolved decisions (2026-05-26)

1. **`confidence` stays a single union** with a `type` discriminator. The
   field-appropriate indicator (quantitative or qualitative) goes in `value`/
   `level`; the required `basis` text does the real judging. Revisit only if a
   first-milestone measurement shows mixing is a real problem. → see C3.
2. **`contested` remains an explicit status** (not derived). C2 forces status +
   `history` updates on every new Evidence, so explicit status cannot drift out
   of sync with the evidence.
3. **Spec amendment requires a human checkpoint even in autonomous mode.**
   → encoded as invariant S5.
