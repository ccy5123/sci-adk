# sci-adk DecisionEngine

> Status: **CONFIRMED (2026-06-15)**. Milestone-2 design for the
> `DecisionEngine` component deliberately deferred by `design/abstractions.md`
> ("Confidence computation engine", abstractions.md:296-307). The eight
> decisions below were confirmed by the user on 2026-06-15; the three flagged
> decisions (D3, D4, D7) and their resolutions are recorded in the Confirmation
> log (§0). No code is created or modified by this document.
> Language-neutral where the schema is concerned; references to Python field
> names (`spec.py`, `evidence.py`, `claim.py`) are the current implementation.

sci-adk is a **research compiler**: it consumes a four-pane proposal and emits a
paper draft + working code + an evidence trail. The deepest design principle is
the separation of **record** (Evidence: monotone, append-only) from **belief**
(Claim: non-monotone, revisable). The `DecisionEngine` is the component that
turns the record into belief *according to the per-Spec rule the user
pre-registered* — never against a global constant. This document specifies it.

---

## 0. Confirmation log (2026-06-15)

The user confirmed all eight decisions. The three flagged decisions resolved as:

- **D3 (interval null value) — CONFIRMED as recommended.** Extend `params` with
  `null_value` + side and make `params` **required for `interval`** (validator
  change in §5). The T-1 fixture's interval rule (`milestone-1.md:144-150`) must
  be updated to carry `params`. Defaulting to 0 stays rejected (D1).
- **D4 (proof / qualitative routing) — CONFIRMED with an OVERRIDE.** Both `proof`
  and `qualitative` route to the LLM-judge (allowed Claude backend) with human
  fallback on low confidence — rather than sending `proof` straight to a human
  checkpoint (the original draft recommendation). Accepted trade-off + safety
  rail: an LLM can affirm a flawed proof with high self-reported confidence, so
  for `proof` the judge MUST attempt a counterexample search and a high-confidence
  "verified" verdict still routes to a lightweight human spot-check before a
  Claim reaches `supported`; low-confidence/contested verdicts escalate to a
  human (D8). See revised Decision 4.
- **D7 (aggregation default) — CONFIRMED as recommended.** Default combine method
  is `latest`; `params` may select `mean`/`pool`. A `proof` counterexample is
  decisive regardless of count.

D1, D2, D5, D6, D8 are accepted as the document recommends. Implementation
proceeds from Phase D1 (engine skeleton).

---

## 1. The gap

The `DecisionRule` type is fully defined, validated, and frozen into the Spec —
but the component that produces Claims **ignores it**.

- `DecisionRule` is a first-class type: `kind ∈ {threshold, bayesian, interval,
  proof, qualitative}`, a human-readable `expression`, and optional `params`
  (`spec.py:94-176`). It is attached to every `Hypothesis` as `decision_rule`
  and invariant S2 forces exactly one per hypothesis (`spec.py:179-205`).
- The evaluator, `ClaimUpdater._evaluate_hypothesis` (`claim_updater.py:83-176`),
  **never reads `hypothesis.decision_rule`**. It counts
  `BearingDirection.SUPPORTS` vs `REFUTES` (`claim_updater.py:106-113`) and sets
  `confidence = support / (support + refute)` (`claim_updater.py:127`),
  flattening every result to `Confidence(type="credence", ...)`
  (`claim_updater.py:145`). The code itself admits this is a placeholder:
  "Milestone 1: Basic evaluation without full DecisionRule engine"
  (`claim_updater.py:30`) and "Full DecisionRule evaluation deferred to
  milestone 2+" (`claim_updater.py:91`).
- `design/abstractions.md:280-292` already names the contract: a
  `DecisionEngine` that "evaluates Claim confidence against Spec
  `decision_rules`, not a binary 0-conjunction quality gate." It is listed under
  "Deliberately left open" as the "Confidence computation engine"
  (`abstractions.md:296-307`).

**Consequence of the gap.** Today, a hypothesis whose pre-registered rule is
`bayesian: "posterior odds > 10 => support"` is evaluated identically to one
whose rule is `interval: "95% CI excludes 0 => support"`: both are reduced to a
headcount of bearing directions. This silently re-introduces exactly the
hardcoded, one-size-fits-all metric the tool policy bans (`tool-policy.md:60-76`;
`abstractions.md:310-317`). The vote-count *is* a global constant in disguise.
The DecisionEngine closes the gap by making the per-Spec `DecisionRule` the sole
authority for direction and confidence.

**Scope note (two-environment separation).** This component is part of the
**sci-adk product runtime** (`src/sci_adk/`), governed by
`design/tool-policy.md` and the Spec/Evidence/Claim abstractions. It is NOT part
of the MoAI-ADK build harness. No LSP "type-correct = done", no coverage
threshold, no conventional-commit gate, and **no hardcoded success metric**
enters the engine — every threshold it uses comes from `DecisionRule.params` of
the Spec under evaluation.

---

## 2. DecisionEngine interface and contract

### 2.1 Signature

The engine answers one question per hypothesis: *given this rule and the
results that bear on it, what direction does the evidence point, and with what
confidence?*

```
DecisionEngine.evaluate(
    rule    : DecisionRule,           // hypothesis.decision_rule (frozen)
    results : EvidenceForHypothesis,  // the bearings + results on one hypothesis
) -> Verdict

Verdict {
    direction  : BearingDirection      // supports | refutes | neutral | inconclusive
    confidence : Confidence            // type + value/level + REQUIRED basis
}
```

`EvidenceForHypothesis` is a thin, pre-filtered view (not a new persisted type):
the list of `(EvidenceItem, Bearing)` pairs whose `Bearing.target_id` equals the
hypothesis id. The engine never reaches into the full Evidence log; the caller
pre-filters (as `ClaimUpdater` already does at `claim_updater.py:67-71`).

`BearingDirection` is reused verbatim from `evidence.py:52-69`
(`SUPPORTS|REFUTES|NEUTRAL|INCONCLUSIVE`). `Confidence` is reused verbatim from
`claim.py:111-169` (`ConfidenceType ∈ {CREDENCE, POSTERIOR, GRADED}`, optional
`value`/`level`, **required `basis`**).

### 2.2 Dispatcher contract

`evaluate` dispatches on `rule.kind` to one handler per `DecisionRuleKind`. Each
handler is a pure function `(rule, EvidenceForHypothesis) -> Verdict`. The engine
itself holds no global state and no constants — all numbers come from
`rule.params`.

```
evaluate(rule, results):
    match rule.kind:
        THRESHOLD   -> _eval_threshold(rule, results)
        BAYESIAN    -> _eval_bayesian(rule, results)
        INTERVAL    -> _eval_interval(rule, results)
        PROOF       -> _eval_proof(rule, results)
        QUALITATIVE -> _eval_qualitative(rule, results)
```

### 2.3 Engine invariants

These are stated in the `abstractions.md` S/E/C style and are numbered D1-D8 for
reference by future evidence and review.

- **D1 (rule authority).** The engine MUST derive `direction` and `confidence`
  from `rule` and the supplied results only. It MUST NOT use any numeric
  constant not present in `rule.params`. A handler that needs a threshold absent
  from `params` returns `inconclusive` with a `basis` naming the missing key —
  it never substitutes a default. (Enforces `tool-policy.md` "no hardcoded
  metric"; `abstractions.md:310-317`.)
- **D2 (basis always present).** Every `Verdict.confidence.basis` is non-empty
  and states which rule, which params, and which results produced the verdict.
  (Mirrors C3, `claim.py:138`.)
- **D3 (null is a verdict).** `refutes`, `neutral`, and `inconclusive` are
  complete, first-class verdicts, never errors or "stuck" states. A rule whose
  condition is not met yields `refutes` or `neutral` per the rule's own
  semantics, not an exception. (Mirrors E2, `evidence.py:52-69`.)
- **D4 (kind → Confidence.type).** The `Confidence.type` the engine emits is a
  function of `rule.kind` (see Decision 5), not always `credence`. The engine
  never invents a type the rule's kind does not imply.
- **D5 (determinism on a fixed record).** For a fixed `(rule, results)` input,
  `evaluate` returns the same `direction` and the same numeric
  `confidence.value`/`level`. Re-running on the *same* Evidence does not move the
  verdict; only *new* Evidence does (this is what makes C1 non-monotonicity
  legible rather than noisy).
- **D6 (aggregation is rule-scoped).** When multiple results bear on one
  hypothesis, the handler for `rule.kind` defines how they combine
  (see Decision 7). There is no engine-wide aggregation policy.
- **D7 (no Spec mutation).** The engine reads the frozen `DecisionRule`; it never
  amends a Spec. Spec amendment remains a human checkpoint (S5,
  `spec.py:374-417`).
- **D8 (escalation over fabrication).** For `proof` and `qualitative` kinds that
  cannot be reduced to a formula, the engine MUST route to an LLM-judge and/or
  human checkpoint (Decision 4). It MUST NOT fabricate a numeric verdict to
  appear decisive. An unresolved judgment yields `inconclusive` with a basis
  requesting the checkpoint.

---

## 3. Open decisions (recommended answer first, then alternatives)

Each decision states a **recommendation**, **alternatives**, and a **rationale**
tied to the record/belief philosophy and the tool policy. None is silently
chosen — a human confirms before implementation.

### Decision 1 — Dispatcher architecture and where it lives

**Recommendation.** Create `src/sci_adk/loop/decision_engine.py` exposing a
`DecisionEngine` class with a single public `evaluate(rule, results) -> Verdict`
and five private `_eval_<kind>` handlers (one per `DecisionRuleKind`). Place it
in `loop/` because `abstractions.md:280-292` calls `DecisionEngine` a loop-level
interface alongside `FeedbackGenerator`, and `ClaimUpdater` already lives in
`loop/`. `ClaimUpdater._evaluate_hypothesis` delegates: it pre-filters Evidence
by hypothesis (as today, `claim_updater.py:67-71`), calls
`engine.evaluate(hypothesis.decision_rule, results)`, then *assembles* the Claim
(id, evidence_set, history, scope_limitations) from the returned `Verdict`. The
engine decides belief; the updater persists it.

**Alternatives.**
1. Put the engine in `core/` next to the types. Rejected: `core/` holds pure
   data types with invariants; the engine is loop behavior, and
   `abstractions.md` already files it under the loop mapping.
2. A registry/strategy map (`kind -> callable`) instead of a `match`. Reasonable
   and slightly more extensible, but for five closed enum kinds a `match`/dispatch
   is simpler and keeps D1 auditable. Recommend keeping the registry option open
   only if a sixth kind is ever added.

**Rationale.** Separating "decide belief" (engine) from "record belief"
(updater + Claim persistence) mirrors the record/belief split itself and keeps
the vote-count removal surgical. Confidence in this decision: **moderate-high** —
location and delegation shape are low-risk; the human input most needed is on
Decisions 3, 4, and 5, which fix *semantics*.

### Decision 2 — Numeric kinds: Result fields + params → direction + confidence

**Recommendation.** Map each numeric kind to specific `Result` fields
(`evidence.py:156-172`) and `rule.params`:

- **threshold.** Compare a statistic to a threshold from params.
  - Reads: `Result.point` (the statistic). Params: a comparison target and
    operator, e.g. `{"statistic": "point", "op": ">=", "value": <x>}` (or a
    convention like `min`/`max`). If `Result.point` is null → `inconclusive`
    (D1/D3).
  - Direction: condition met → `supports`; cleanly not met → `refutes`; missing
    operand → `inconclusive`.
  - Confidence: `type=credence`, `value` a monotone function of margin
    (how far past/short of threshold), `basis` quotes statistic, op, and value.
- **bayesian.** Compare posterior odds to a params threshold.
  - Reads: `Result.posterior` (a probability in [0,1], `evidence.py:165`).
    Convert to odds `p/(1-p)`. Params: `{"min_odds": <k>}` (the rule's own
    "posterior odds > k => support", `spec.py:109-113`).
  - Direction: odds ≥ `min_odds` → `supports`; odds ≤ `1/min_odds` (symmetric
    evidence against) → `refutes`; between → `neutral`/`inconclusive` per a
    params flag.
  - Confidence: `type=posterior`, `value = Result.posterior`, `basis` quotes the
    odds and `min_odds`.
- **interval.** Does the CI exclude the rule's null value?
  - Reads: `Result.ci = [lower, upper]` (`evidence.py:161`). Null value source is
    **Decision 3**.
  - Direction: CI entirely above/below null and on the rule's "support" side →
    `supports`; CI contains null → `neutral`/`null` (the rule's "includes 0 =>
    null", `spec.py:109-113`); CI excludes null on the refute side → `refutes`.
  - Confidence: `type=credence`, `value` from interval width/position relative to
    null (narrow CI far from null → higher), `basis` quotes the CI and the null
    value used.

**Alternatives.**
1. Parse the numeric thresholds out of `rule.expression` (the human text)
   instead of `params`. Rejected as the primary path: text parsing is brittle
   and violates the spirit of D1 (machine-usable numbers belong in `params`).
   Keep as a *fallback* only if `params` is absent (see Decision 3).
2. A single generic numeric handler keyed by an operator in params, with
   `kind` only labeling the Confidence.type. Simpler code, but collapses the
   meaningful distinction the user pre-registered between (say) a Bayesian and an
   interval rule, weakening the basis text. Rejected.

**Rationale.** Each kind reads exactly the `Result` fields its statistic lives
in, and every number comes from `params` — so the metric stays per-Spec. The
margin-based confidence keeps `value` continuous (not binary), honoring S3 and
C-confidence-is-continuous. Confidence: **moderate** — the field mappings are
sound, but the exact confidence formulas (margin → value) are tuning the human
may want to weigh in on; they are intentionally simple and documented as
revisable.

### Decision 3 — Where does an `interval` rule get its null value?

**Problem.** `interval`, `proof`, and `qualitative` rules currently require **no
params** — only `threshold` and `bayesian` are forced to have params
(`spec.py:157,171`). So an interval rule like "95% CI excludes 0 => support" has
no *machine-readable* null value; "0" lives only in the human `expression`.

**Recommendation.** **Extend `params` for `interval` rules** to carry the null
value and side, e.g. `{"null_value": 0.0, "support_side": "excludes"}` (or
`"above"/"below"`). Make `params` **required for `interval`** the same way it is
for `threshold`/`bayesian`, by adding `INTERVAL` to the validator set (this also
folds into the cleanup in §5). When `null_value` is absent, the engine returns
`inconclusive` with a basis naming the missing key (D1) — it does **not** assume
0.

**Alternatives.**
1. Parse the null value from `rule.expression` with a small, well-tested regex
   (e.g. find "excludes <number>"). Pro: no schema change, works on existing
   T-1 fixtures whose interval rule has no params (`milestone-1.md:144-150`).
   Con: brittle, locale/format-sensitive, and pushes a machine number into free
   text. Recommend ONLY as a fallback when `params.null_value` is absent, behind
   a logged warning, never as the primary source.
2. Default the null value to 0 when absent. **Rejected** — that is a hardcoded
   metric (D1 violation), exactly what the tool policy forbids.

**Rationale.** A pre-registered interval rule's null value is part of the
*contract*; storing it in `params` makes the contract machine-checkable and keeps
the engine constant-free. This decision **most needs human input** because it
changes a validator (Spec compilation behavior) and may require updating the T-1
fixture in `milestone-1.md:144-150` to add `params`. Confidence: **medium** on
the recommendation, **high** that defaulting to 0 is wrong.

### Decision 4 — Non-numeric kinds (`qualitative`, `proof`): route to judge / human

**Recommendation.** [CONFIRMED 2026-06-15 — OVERRIDE of the original draft. The
user chose to route BOTH `proof` and `qualitative` to the LLM-judge with human
fallback, instead of sending `proof` directly to a human checkpoint. Safety rail
for `proof`: the judge MUST attempt a counterexample search, and a high-confidence
"verified" verdict still routes to a human spot-check before a Claim reaches
`supported`; low-confidence verdicts escalate to a human. The `proof` bullet
below (direct human checkpoint) is SUPERSEDED by this note.] Neither kind reduces
to a formula, so the engine routes them instead of computing:

- **proof.** Reads `Result.finding` / `Result.artifact_ref` and the bearing
  `kind` (`EvidenceKind.PROOF_STEP` or `COUNTEREXAMPLE`, `evidence.py:45-49`). If
  a verified derivation is present → `supports`; a counterexample → `refutes`;
  otherwise route to a **human checkpoint** (proof verification is the canonical
  case where autonomy yields to a human, consistent with S5's spirit). Emit
  `Confidence(type=graded, level=strong, basis="verified derivation in <ref>")`
  on support, or `inconclusive` pending the checkpoint (D8).
- **qualitative.** Route to an **LLM-judge** (Claude Code, allowed by
  `tool-policy.md:26-28`) that reads `rule.expression` (the prose criterion),
  the `Result.finding` text, and any `params`, and returns a graded level + a
  basis. The judge prompt is fed the rule's own criterion — it applies the
  *Spec's* standard, never a global rubric. Human escalation when the judge is
  low-confidence.

In both cases the engine reads the Spec's rule/params and external context only
through allowed tools; it introduces no new tool and no global standard.

**Alternatives.**
1. Always escalate both kinds to a human, no LLM-judge. Safer for `proof`,
   but for `qualitative` it makes autonomous runs stall on every soft criterion.
   Recommend human-only for `proof`, judge-with-human-fallback for `qualitative`.
2. Map `qualitative` to a fixed graded scale by keyword-matching the finding.
   **Rejected** — that is a smuggled global rubric (D1) and loses the
   field-specific judgment the `basis` is supposed to carry (C3).

**Rationale.** "No formula" must mean "route", not "fake a number" (D8). Using
the allowed LLM backend for the soft case, and a human checkpoint for proofs,
keeps the engine inside the tool policy and inside the record/belief discipline
(the judge's output becomes a documented `basis`, not an unexplained score).
This decision **needs human input** on the proof→human-vs-judge boundary and on
whether the LLM-judge call belongs in the engine or in a separate
`FeedbackGenerator`-adjacent component.

### Decision 5 — `Confidence.type` mapping per kind

**Recommendation.** Stop flattening everything to `credence`
(`claim_updater.py:145`). Map by kind:

| `DecisionRuleKind` | `ConfidenceType` | `value` / `level` source |
|--------------------|------------------|--------------------------|
| `bayesian`         | `posterior`      | `value = Result.posterior` |
| `threshold`        | `credence`       | `value` from margin past threshold |
| `interval`         | `credence`       | `value` from CI position vs null |
| `proof`            | `graded`         | `level = strong` (verified) / else routed |
| `qualitative`      | `graded`         | `level` from LLM-judge / human |

`basis` is **always** populated (D2, mirroring C3, `claim.py:138`). `graded`
verdicts set `level` and leave `value` null; `posterior`/`credence` set `value`
and leave `level` null — matching the `Confidence` validators
(`claim.py:143-156`).

**Alternatives.**
1. Keep a single `credence` everywhere and let `basis` carry the nuance. This is
   what abstractions.md "Resolved decision 1" tolerates for the *type union*
   (`abstractions.md:319-324`), but it discards the honest signal that a Bayesian
   posterior is a posterior. Rejected for the engine, which knows the kind.
2. Add a new `ConfidenceType` for intervals. Rejected — the existing three types
   cover the cases; adding types expands surface for little gain
   (`tool-policy.md:78-86` conservatism).

**Rationale.** The type should reflect what the rule actually computed; this
keeps the paper's confidence statements truthful to method. It stays within the
existing `ConfidenceType` enum, so no core type change. Confidence: **high** —
this is a faithful, low-risk mapping; the only nuance the human may want is
whether `interval` should also be `posterior` when the CI is credible (Bayesian)
rather than frequentist; if a Spec declares that, params can carry it.

### Decision 6 — Does the engine consume `Bearing.weight`?

**Recommendation.** **Yes** — use `Bearing.weight` (`evidence.py:215`) as a
per-result multiplier inside each kind's aggregation (Decision 7), defaulting to
`1.0` when null. Today `total_weight` is computed and then thrown away
(`claim_updater.py:104,109`); the design says weight is "the strength of this
bearing" (`abstractions.md:174`). The engine uses it as a weight in
weighted aggregation (e.g. weighted mean of posteriors, weighted vote for
threshold margins), never as a hidden global constant — weight is per-Evidence
data, not a tuning knob.

**Alternatives.**
1. Ignore weight (treat all bearings equally) until a Spec demonstrably needs it.
   Simpler, and weight is optional in the schema. But it leaves a designed field
   permanently dead and recreates the equal-vote flaw. Recommend wiring it in but
   documenting that weight defaults to 1.0 so single-weight Specs behave
   intuitively.
2. Let each `rule.params` opt into weighting (`{"use_weight": true}`). More
   explicit, more surface. Defer unless a Spec needs to *disable* weighting.

**Rationale.** Weight is record data (it lives on the immutable Evidence), so
consuming it does not violate D1 — it is not a global metric, it is part of what
happened. Confidence: **medium** — the human may prefer to defer weighting until
a real Spec needs differential evidence strength; flagged accordingly.

### Decision 7 — Multi-evidence aggregation into one Claim status + confidence

**Recommendation.** Aggregation is **rule-scoped** (D6), not a global count:

- **threshold / interval / bayesian:** combine the per-result statistics first,
  then apply the rule once. E.g. bayesian: weighted-combine posteriors (or take
  the most recent posterior if results are sequential updates) → one odds → one
  direction; interval: combine CIs (meta-analytic pooling or, minimally, use the
  latest/tightest) → one interval vs null; threshold: weighted mean of the
  statistic vs threshold. The combination method is itself a `params` option
  (e.g. `{"combine": "latest" | "mean" | "pool"}`), defaulting to `latest`
  (the most recent Evidence is the current best estimate) when absent.
- **proof:** a single verified derivation suffices for `supports`; a single
  valid counterexample forces `refutes` (a counterexample is not outvoted by
  supportive runs — it is decisive). This is asymmetric *by the nature of
  proof*, encoded in the proof handler, not a global rule.
- **qualitative:** the LLM-judge sees all findings at once and returns one graded
  verdict + basis.

**Alternatives.**
1. Keep naive counting (current behavior) for numeric kinds too. Rejected —
   that is the very flaw this engine removes.
2. Always use only the single most-recent Evidence item, ignoring earlier ones.
   Simple and matches "latest is current belief", but discards corroboration.
   Recommend `latest` only as the *default*, with `mean`/`pool` available via
   params.

**Rationale.** Different statistics combine differently; forcing one aggregation
on all of them is the hidden-constant trap again. Making the combine method a
`params` choice keeps it per-Spec. The proof asymmetry honors how mathematics
actually works (one counterexample refutes). This decision **needs human input**
on the default combine method and on the proof asymmetry. Confidence: **medium**.

### Decision 8 — Non-monotone updates: moving status and appending history

**Recommendation.** Re-running the engine as new Evidence arrives must be able to
**demote** a Claim, and every move must be recorded. The updater:

1. Loads the existing Claim for the hypothesis if one exists (today it always
   creates fresh — see §6).
2. Calls `engine.evaluate(rule, all_results_so_far)` over the full, append-only
   set of bearings on the hypothesis (record is monotone; belief is recomputed).
3. Maps `Verdict.direction` → `ClaimStatus`: `supports`→`supported`,
   `refutes`→`refuted`, mixed (the rule/aggregation reports both sides
   meaningfully)→`contested`, `neutral`/`inconclusive`→keep `proposed` or move to
   `contested` per the rule.
4. If the new status differs from the current one, calls the existing
   `Claim.update_status(new_status, triggered_by=<latest evidence id>, note=...)`
   which appends a `StatusChange` (`claim.py:299-329`) — satisfying C1 (any
   direction) and C2 (append-only history). `supported → contested → refuted` is
   a legal, expected path, not a regression.
5. Updates confidence via `Claim.update_confidence(...)` (`claim.py:354-396`),
   keeping `basis` required.

`retracted` is reserved for provenance failure (broken `code_ref`, failed
reproduction), not for ordinary evidence shifts — the engine does not emit
`retracted`; that is a separate provenance check (out of scope here, flagged).

**Alternatives.**
1. Always create a new Claim per run (today's behavior, `claim_updater.py:138`,
   `_generate_claim_id` returns a stable `claim-<hyp.id>` so it overwrites the
   file but loses in-memory history). Rejected — it cannot demote with history;
   it just replaces, violating the spirit of C2.
2. Make the engine itself own status transitions. Rejected — D7/separation: the
   engine returns a `Verdict`; the Claim type already owns transition mechanics
   (`update_status`), and that is where C1/C2 are enforced.

**Rationale.** Non-monotone belief over a monotone record is the core thesis
(`abstractions.md:15-48`). Recomputing the verdict over the full record each time
and threading it through `Claim.update_status` makes demotion a first-class,
audited event. Confidence: **high** on the mechanism (the Claim type already
supports it); **medium** on the exact direction→status mapping for `neutral`
(proposed vs contested), which the human may want to pin down.

---

## 4. ClaimUpdater refactor plan

The refactor is surgical and removes the vote-count, delegating to the engine.

1. **Introduce** `src/sci_adk/loop/decision_engine.py` with `DecisionEngine`,
   `Verdict`, and the five `_eval_<kind>` handlers (Decision 1). No change to
   `core/` types except the validator extension in §5 / Decision 3 (pending
   human confirmation).
2. **In `ClaimUpdater._evaluate_hypothesis`** (`claim_updater.py:83-176`):
   - Delete the support/refute counting block (`claim_updater.py:101-129`),
     including the dead `total_weight` (§5).
   - Build `EvidenceForHypothesis` from the already-filtered `evidence_items`
     (the filter at `claim_updater.py:67-71` stays).
   - Call `verdict = self.engine.evaluate(hypothesis.decision_rule, results)`.
   - Map `verdict.direction → ClaimStatus` (Decision 8) and use
     `verdict.confidence` directly (it already carries the kind-correct type and
     a required basis — replacing the hardcoded `type="credence"` at
     `claim_updater.py:145`).
3. **For an existing Claim**, switch from "always create" to
   "load-or-create, then `update_status` / `update_confidence`" so demotion +
   history work (Decision 8). For Milestone-1 parity, first-evaluation behavior
   is preserved (a fresh Claim with one `StatusChange`).
4. **`evidence_set`** assembly (`claim_updater.py:149-161`) is unchanged in
   spirit — supporting vs refuting links per bearing — but reads the direction
   from the bearing as before; it is record-keeping, not belief, so it stays.
5. **`scope_limitations`** stops being the hardcoded Milestone-1 string
   (`claim_updater.py:162`) and is left to the caller / a later renderer concern;
   the engine does not set it.

No public signature of `update_claims` / `update_claims_from_evidence` changes,
so callers and existing tests of the I/O path keep working; only the belief
computation is replaced.

---

## 5. Cleanup: incidental defects found around DecisionRule

These were found while reading the code and are recorded here so they are not
lost. They are small and can be folded into the engine work (items 1-2 touch
Spec validation; item 3 disappears with the refactor in §4).

1. **No-op expression validator** — `spec.py:129-146`
   `validate_expression_not_binary_only` builds a `binary_patterns` list, loops
   over it, and `pass`es on every match. It enforces nothing and returns `v`
   unchanged. Either make it warn meaningfully (it cannot reject per S3) or
   remove it. Recommend: keep S3 as documentation, delete the dead loop, or have
   it attach a structured warning the compiler surfaces — but not a silent
   `pass`.
2. **Duplicate validators** — `spec.py:148-162` (`validate_params_match_kind`)
   and `spec.py:164-176` (`validate_params_required_for_kind`) are the *same*
   check ("threshold/bayesian require non-empty params"), both
   `model_validator(mode="after")`. One should be removed. When implementing
   Decision 3, the surviving validator is the natural place to add `INTERVAL` to
   the required-params set.
3. **Dead `total_weight`** — `claim_updater.py:104,109` accumulates
   `total_weight` and never reads it. It vanishes when the counting block is
   deleted in §4. (Note: `Bearing.weight` itself is *not* dead — Decision 6 wires
   it into the engine; only this orphaned accumulator is.)

---

## 6. Phase plan

Phases are ordered by dependency; no time estimates (per project convention).

- **Phase D0 — Confirm open decisions.** Resolve Decisions 1-8 with the human,
  especially 3 (interval null source, changes a validator + maybe the T-1
  fixture), 4 (proof/qualitative routing), and 7 (aggregation default). Update
  this doc's status to CONFIRMED only after sign-off.
- **Phase D1 — Engine skeleton.** Add `decision_engine.py` with `evaluate`
  dispatch, `Verdict`, and stub handlers returning `inconclusive` + basis.
  Establish invariants D1-D8 as the handler contract.
- **Phase D2 — Numeric kinds.** Implement `threshold`, `bayesian`, `interval`
  per Decisions 2, 3, 5, 6, 7. Extend the Spec validator for `interval` params
  (Decision 3) and do cleanup items 1-2 (§5).
- **Phase D3 — Non-numeric kinds.** [IMPLEMENTED 2026-06-16, engine-side]
  Both `proof` and `qualitative` route to an injected `Judge` (Decision 4 + §0
  override) — `loop/judge.py` defines the `Judge` Protocol + `JudgeVerdict`;
  `DecisionEngine(judge=...)` consumes it. Rails enforced in the engine: a
  counterexample (in the record or judge-found) refutes decisively; a confident
  proof "verified" verdict does NOT become `supports` — it returns `inconclusive`
  pending a human spot-check; low confidence escalates; with no judge it returns
  `inconclusive` (never fabricated, D8). The live Claude-backed `Judge` adapter
  (`ClaudeJudge`) is **deferred** — the runtime Claude-invocation is a separate
  infra decision; tests inject a fake `Judge`.
- **Phase D3b — Machine-checked proofs (FORMAL_PROOF), Decision 4 EXTENSION [IMPLEMENTED
  2026-07-02].** Decision 4's §0 human spot-check exists because the proof judge is an
  *LLM* (which misjudges proofs). A proof machine-checked by a TRUSTED EXTERNAL CHECKER
  (Lean 4 + Mathlib) is different: its kernel result is a mechanical RECORD fact, not a
  belief. So a new `EvidenceKind.FORMAL_PROOF` (the dual of `COUNTEREXAMPLE`) is DECISIVE
  supports in `_eval_proof` — no LLM-judge, no §0 human spot-check — and `verify` re-derives
  it from the record (re-run the checker) with no LLM. Order: the counterexample check runs
  FIRST, so a contradictory record (both a machine proof AND a counterexample) safety-refutes.
  This does NOT weaken §0 (an LLM "verified" still routes to a human); it adds a stronger,
  autonomous path for mechanically-checked proofs — the machine-checked resolution of the
  PROOF→SUPPORTED gap the field report (P1) raised. Adapter seam: `adapter/lean_capability.py`
  (`LeanProofTask` + `lean_experiment`, executor-injectable; PASS→FORMAL_PROOF, FAIL→a
  NEUTRAL PROOF_STEP — a failed compile is not a counterexample). Checker image recipe:
  `environments/lean-base/Dockerfile` (RECIPE only — Lean+Mathlib is multi-GB, built by the
  user, not in CI).
- **Phase D4 — Updater delegation.** Refactor `ClaimUpdater._evaluate_hypothesis`
  to delegate (§4), including load-or-create + non-monotone `update_status`
  (Decision 8). Remove dead `total_weight` (§5 item 3).
- **Phase D5 — Verification on the record.** [IMPLEMENTED 2026-06-16]
  `tests/test_t1_end_to_end.py`: (1) a real Docker T-1 run → Evidence → engine →
  Claim, where a threshold rule on the encoding count drives the SUPPORTED
  verdict (basis quotes the rule, not a vote); (2) the canonical T-1 interval
  rule drives the verdict from a CI, and a synthetic refuting Evidence (CI below
  null, arriving later) demotes the SUPPORTED Claim to REFUTED with a new
  `StatusChange` (non-monotone, C1/C2). Engineering-layer tests; the Docker test
  skips when the docker CLI is absent.

---

## 7. Summary of recommendations

| # | Decision | Recommended answer |
|---|----------|--------------------|
| 1 | Dispatcher / location | New `loop/decision_engine.py`; `match` on `rule.kind`; `ClaimUpdater` delegates and only assembles the Claim |
| 2 | Numeric mapping | threshold←`point`+op/value; bayesian←`posterior`→odds vs `min_odds`; interval←`ci` vs null; margin-based continuous confidence |
| 3 | Interval null value | Extend `params` (`null_value`+side), require params for `interval`; expression-parse only as fallback; never default to 0 |
| 4 | Non-numeric kinds | [CONFIRMED, override] BOTH proof & qualitative→LLM-judge (Claude); for proof the judge does a counterexample search + human spot-check on a high-confidence "verified" verdict; human fallback on low confidence; never fabricate a number (D8) |
| 5 | Confidence.type | bayesian→posterior, threshold/interval→credence, proof/qualitative→graded; `basis` always required |
| 6 | Bearing.weight | Consume it as a per-result multiplier (default 1.0); it is record data, not a global metric |
| 7 | Aggregation | Rule-scoped: combine statistics then apply rule once; combine method via `params` (default `latest`); proof counterexample is decisive |
| 8 | Non-monotone | Recompute verdict over full record, map direction→status, thread through `Claim.update_status` so demotion appends `StatusChange` (C1/C2) |

---

Status: CONFIRMED (2026-06-15) — D3/D4/D7 resolved (D4 by user override); D1/D2/D5/D6/D8 accepted as recommended
Implementation (2026-06-16, on master): **D1-D5 all done** (Milestone-2
complete). D2 numeric kinds; D3 proof/qualitative judge routing (engine-side;
live ClaudeJudge deferred); D4 ClaimUpdater delegation + non-monotone updates;
D5 T-1 end-to-end (real Docker → Claim + interval-rule non-monotone demotion),
Docker now available. Follow-ups: live ClaudeJudge backend; the human-spot-check
step that promotes a pending-verified proof to `supported`.
Source: gap between `DecisionRule` (spec.py:94-205) and the vote-count
placeholder (claim_updater.py:83-176); interface named in abstractions.md:280-307
Last Updated: 2026-06-16
