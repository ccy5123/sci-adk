# Evidence Validity (referent-typed enforcement)

> Status: AUTHORITATIVE on evidence validity (2026-06-17).
> Cross-ref: `design/abstractions.md` (record vs belief; Evidence/Claim invariants),
> `design/sci-adk-productization-plan.md` §7 (agents propose, the engine judges;
> no self-certification), `design/adoption-roadmap.md` (rigor as the product).
> Source defect: a run on an EMPIRICAL proposal (rice organ dry-weight) used
> SYNTHETIC data and the harness reported "4/4 SUPPORTED / validated milestone".

---

## 0. The defect this exists to prevent

A research run was given an empirical proposal (predict rice organ dry-weight from
measured plant traits). No measured data was acquired. The pipeline generated
synthetic numbers directly, the literature halt was advisory (and was bypassed by
generating data rather than acquiring it), and the engine rendered **4 of 4
hypotheses SUPPORTED** with a "validated milestone" summary.

That is the exact rigor failure sci-adk exists to prevent: a **self-certified,
ungrounded result**. Nothing in the record distinguished a fabricated stand-in for
real plant measurements from real plant measurements, so belief about an empirical
referent was affirmed against data that does not contain that referent.

This note fixes it by making evidence validity a **referent-typed, load-bearing
gate** — not an advisory flag, not something an agent can route around by
generating data.

---

## 1. The principle

The line for whether generated/synthetic data is valid Evidence for a Claim is
**NOT synthetic-vs-real**. Plenty of legitimate science runs entirely on generated
instances. The line is:

> Does the data genuinely **INSTANTIATE** the claim's referent, or does it
> **PROXY** an external referent it does not contain?

- A claim about a **formal** object (a math statement, an algorithm, a data
  structure, the *behavior of an algorithm*) is *about* the very thing you can
  generate. Generated instances ARE that thing. They are genuine evidence.
- A claim about an **empirical** referent (rice plants, patients, a physical
  phenomenon) is *about* something outside the program. A generated number is a
  **stand-in** for a measurement of that external thing; it does not contain the
  thing. It cannot be evidence for the empirical claim.

This is a direct application of `design/abstractions.md`'s organizing principle
(record vs belief): the **record** may hold anything that was produced; **belief**
about an empirical referent may only be affirmed from data that contains that
referent. The gate protects belief, not the record.

### T-1 is the legitimate formal case

T-1 (the molecular Gödel encoding) tests **injectivity over generated molecules**.
The hypothesis is *about* the encoding map `phi: G -> N` — a formal object. The
generated molecule set IS the population the claim quantifies over (on the tested
set). A zero collision count over those generated graphs is a **real
computational result**, not a synthetic proxy for anything external. So T-1 is
`referent = formal`, `data_source = generated`, and it is genuine evidence.

---

## 2. The three guards

### Guard 1 — Referent class (E1)

Every `Hypothesis` carries a frozen `referent`:

- `formal` — math, algorithms, CS theory, ML *algorithm-behavior*; generated
  instances instantiate the referent.
- `empirical` — physical/biological/clinical phenomena; the referent lives
  outside the program and must be **measured**.

`referent` is **frozen in the Spec** (anti-HARKing): you cannot relabel an
empirical hypothesis as formal *after* seeing results to dodge the data
requirement. The default is **`empirical`** — fail-closed. An unmarked hypothesis
is treated as the strictest case (real data required), so forgetting to declare a
referent can never silently *weaken* the gate.

### Guard 2 — Non-circularity attestation (formal/generated)

A `formal` hypothesis backed by `generated` evidence carries a required, non-empty
**non-circularity statement**: *what does the verifier test that is NOT baked into
the generator?*

This is the difference between a result and a tautology:

- Legitimate (T-1): collisions **could** occur — the generator emits molecular
  graphs without any guarantee of distinct codes; the verifier independently checks
  for collisions. A zero count is therefore informative.
- Circular (banned-in-spirit): "fit the curve family you generated the data from,
  then claim you discovered that family." The verifier only re-confirms a property
  the generator guaranteed; the result carries no information.

The harness does **not prove** non-circularity. It **records and surfaces** it: a
formal/generated hypothesis with no attestation surfaces an agent checkpoint (an
honest limit, not an auto-proof). This matches §7's "agents propose, the engine
judges" — the engine records the attestation and demands one; it does not certify
the claim is genuinely non-circular.

### Guard 3 — Proxy-ban (E3, the load-bearing halt)

Applied where Evidence bears on a hypothesis (claim derivation), as a **HARD halt**
— a real stop, not an advisory flag:

1. Any `synthetic_proxy` Evidence bearing on an **`empirical`** hypothesis →
   **HALT** (category error: fabricated stand-in for an external referent).
   Unconditional — even a neutral bearing halts, because the fabrication itself is
   the error.
2. An **`empirical`** hypothesis whose bearing Evidence yields a **binding verdict**
   (SUPPORTS / REFUTES) with **no `measured` item** (all `generated` /
   `synthetic_proxy` / `None`) → **HALT** (no real data — the rice failure stops
   here). The binding-only scope is deliberate: a NEUTRAL / INCONCLUSIVE bearing
   that yields a `proposed` Claim affirms no belief, so an empirical hypothesis may
   legitimately sit awaiting real data (e.g. literature context recorded, or an
   agent checkpoint open) without halting. Belief is gated; the record is not.
3. `generated` Evidence on a **`formal`** hypothesis → **allowed** (T-1).

The halt is a typed error (`ValidityHalt`) raised by the kernel at the
claim-derivation chokepoint, caught by the CLI → friendly stderr + non-zero exit.
Because it fires inside the Evidence→Claim derivation, it is **impossible to route
around by generating data**: generating data is precisely what trips it.

---

## 3. The data-source taxonomy (E2)

Every `Provenance` carries a `data_source`:

- `measured` — real empirical data (instrument readings, field measurements,
  clinical records). The only kind that satisfies an empirical claim.
- `generated` — an in-silico / computed **genuine instance** of a formal referent
  (T-1's molecule set; a synthetic benchmark for an algorithm's behavior).
- `synthetic_proxy` — a **fabricated stand-in** for an external referent the data
  does not contain (the rice numbers).
- `None` — unstated. Treated as **"not measured"** by the gate (fail-closed): a
  binding empirical verdict with only `None`-sourced evidence halts exactly as it
  would for `generated`.

`generated` vs `synthetic_proxy` is the operative distinction, and it is a property
of *what the data is about*, not of how it was produced. The same RNG call is
`generated` when it instantiates a formal referent and `synthetic_proxy` when it
impersonates a measurement.

---

## 4. Reporting

Results are labelled by `referent` + `data_source`, never a bare "supported" for
synthetic-on-empirical:

- `formal` + `generated` → "in-silico / computational result" (e.g. T-1).
- `empirical` + `measured` → an empirical result (the only empirical "supported").
- a blocked `synthetic_proxy` → `empirical`, or a binding empirical verdict with no
  measured item → the **halt message** (no claim is recorded).

A bare "supported" can never be emitted for an empirical claim whose only evidence
is synthetic/generated — the gate stops it before a Claim is written.

---

## 5. Honest limits

- The gate enforces **data adequacy by referent class**. It does NOT verify that
  `measured` data is correctly measured, nor that a `formal`/`generated` result is
  genuinely non-circular — both are recorded/surfaced, not auto-proven (§7).
- `referent` and `data_source` are declarations. Their integrity rests on the Spec
  being frozen (referent cannot be relabelled post-hoc) and on honest provenance.
  The gate makes the *honest* declaration load-bearing; it cannot detect a
  deliberately mislabelled `synthetic_proxy` claimed as `measured`. That residual
  trust is the same trust every provenance field already carries (E3).

---

## 6. Calibration / method hypotheses

Generated data is valid evidence for a hypothesis that is *explicitly about the
method or calibration itself* (e.g. "the simulator reproduces the analytic
solution", "the estimator is unbiased on synthetic draws"). Such a hypothesis is
`formal` (it is about the algorithm/method's behavior), so it passes Guard 3 item 3
and carries a non-circularity attestation under Guard 2. It is NOT a license to
mark an empirical phenomenon supported from synthetic data — that remains a
category error under Guard 3 item 1/2.

---

Version: 1.0.0
Status: AUTHORITATIVE
Last Updated: 2026-06-17
