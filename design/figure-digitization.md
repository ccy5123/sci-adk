# sci-adk — Figure Digitization (DESIGN RECORD)

> Status: **DESIGN RECORD ONLY** (2026-06-17). **Not implemented** — no code, no tests, no
> schema change, no tool integration. This note pins the agreed design so it can be pulled
> when the trigger fires.
>
> Classification: `adoption-roadmap.md` **B-bucket** (borrow-later capability plugin).
> **Trigger (not yet fired):** a chosen problem's domain requires **figure-only data**
> (authors published no raw data and no in-text/table values), AND the MVP exact-verifier
> is already in place. Until then, this stays a document.
>
> Cross-refs (checked): `design/evidence-validity.md` (the gate this EXTENDS — referent-typed
> validity, "agents propose, engine judges, no self-certification"), `design/abstractions.md`
> (Evidence/Claim, record≠belief, E-invariants), `design/adoption-roadmap.md` (B-bucket;
> borrow-not-reimplement; "does it touch the verdict path?"), `design/literature-acquisition.md`
> (acquisition + the fidelity hierarchy below).

---

## 1. Extraction fidelity hierarchy — digitize is the LAST resort

When a value is needed, try top-down; only descend when the level above is absent:

- **(a) Author raw data** — Supporting Information, data repositories (Zenodo, figshare),
  "data availability" statements. **Always checked BEFORE digitizing.**
- **(b) Body / table explicit numbers** → `reported`. Measured-grade: the value is stated,
  no reconstruction.
- **(c) Figure digitization** → `digitized`. **Lossy; only when (a) and (b) are absent.**

`measured` (real measurement) and `reported` (explicit stated value) are trustworthy-grade
and stay as they are. Only `digitized` carries reconstruction risk and needs the new gate.

---

## 2. `digitized` is a new Evidence kind (asymmetric adoption)

Leave `measured`/`reported` as-is; introduce a **new gated kind only for `digitized`**.
Rationale — only `digitized` carries obligations the others do not:

1. it must **never auto-promote to `measured`**,
2. it **cannot be counted before independent verification**,
3. it **carries reconstruction uncertainty** intrinsically.

Principle (same as the evidence-validity work): *elevate to a type only what needs the
gate* — don't grow surface without a consumer. measured/reported don't need this gate;
digitized does.

---

## 3. Stateful type (lifecycle)

```
proposed   (extracted, NOT yet independently verified)   →   verified   (passed verification)
```

A `proposed` digitized item is **not evidence-grade** — it is a candidate. Only `verified`
digitized data may influence a Claim.

---

## 4. Schema (fields) — `EvidenceItem(kind="digitized")`

| field | meaning |
|-------|---------|
| `quantity` | what value this is |
| `value`, `unit` | the extracted measurement |
| `source` | provenance of origin — Fig X, DOI / run |
| `method` | `deterministic` \| `vlm` — **v1 implements `deterministic` only; `vlm` is reserved/unimplemented** |
| `axis_calib` | axis calibration values (deterministic path) |
| `read_uncert` | read uncertainty (marker size / resolution / log-axis effects) |
| `state` | `proposed` \| `verified` |
| `verification` | `{ method: replot \| human \| judge, verifier_id, result, artifact }` |

---

## 5. Gate (kernel: DecisionEngine + `verify`)

This **extends** `evidence-validity.md` (the self-certification ban: agents propose, the
engine judges; the verdict path stays deterministic). For the `digitized` kind:

- **No auto-promotion to `measured`** — anti-laundering. Because it is a separate kind, the
  promotion is *structurally* impossible, not merely discouraged.
- A `proposed` digitized item is **excluded from `DecisionRule` evaluation** (it is not
  evidence-grade).
- To be **counted**, a digitized item must be `verified` **and** record **extractor ≠
  verifier** — the self-certification ban applied to this kind (the one who read the value
  off the plot may not also be the one who certifies it).
- **`sci-adk verify` (headless)** re-confirms that every *counted* digitized item is
  `verified` and carries an independent-verifier record.
- **`record_digest` MUST cover the verification artifact** too, so tampering with the
  verification (not just the value) is caught.

---

## 6. Build vs borrow (when the trigger fires)

- **Build (kernel):** the `digitized` Evidence kind schema (§4) + the gate (§5).
- **Borrow (capability plugin, behind the adapter — never reimplemented in the kernel):**
  - digitization *execution* — a deterministic digitizer (WebPlotDigitizer-style: axis
    calibration by a human/agent, point extraction by pixel position);
  - replot-*verification* execution (overlay the extracted points back on the original
    figure for the independent check).
- The gate is **method-agnostic**, so a future `vlm` method can plug in **behind the same
  gate** if a real bottleneck appears — the design is not future-foreclosed.

---

## 7. `vlm` deferred — rationale (recorded)

`method="vlm"` is reserved but **not built**, deliberately:

- The verification gate already eats most of a VLM's time savings: an independent check
  ≈ doing the deterministic digitization anyway. So a VLM adds **hallucination risk** for
  **marginal net gain**.
- Local chart models (DePlot / ChartGemma / UniChart family) = **infrastructure too heavy**
  for the payoff. A hosted VLM is cheap but the marginal utility is still small.
- Conclusion: **defer; keep `vlm` reserved in the `method` enum.** The one place a VLM is
  comparatively safe is **axis-label / legend / caption OCR** — *not* value extraction off
  the plotted curve.

---

## 8. When the trigger fires — pull list

1. Add the `digitized` Evidence kind + schema (§4) to `core/evidence.py`.
2. Add the gate (§5) at the claim-derivation chokepoint (mirror the evidence-validity gate
   in `loop/claim_updater.py`) + extend `verify` + `record_digest`.
3. Add the deterministic digitizer + replot-verifier as a **capability plugin** (adapter).
4. Tests: proposed-excluded-from-eval; verified-with-extractor≠verifier counts; auto-promote
   blocked; verify re-confirms; digest covers verification artifact; fidelity hierarchy
   (author-raw → reported → digitized) honored.

---

## 9. References

Design (internal):
- `design/evidence-validity.md` — the validity gate this extends (referent-typed; no self-cert).
- `design/abstractions.md` — Evidence/Claim, record≠belief, E-invariants.
- `design/adoption-roadmap.md` — B-bucket classification; borrow-not-reimplement; verdict-path test.
- `design/literature-acquisition.md` — acquisition + prior-work; the fidelity hierarchy's home.

Candidate external tools (borrow part; surveyed 2026-06, user-relevant — not adopted here):
- WebPlotDigitizer (deterministic digitizer): https://github.com/automeris-io/WebPlotDigitizer
- pdffigures2 (locate/crop figures from scholarly PDFs): https://github.com/allenai/pdffigures2
- DePlot / ChartGemma (VLM chart→table — *deferred per §7*): https://arxiv.org/pdf/2212.10505 , https://arxiv.org/pdf/2407.04172

---

Version: 1.0 (DESIGN RECORD — not implemented)
Source: figure-digitization design decision (2026-06-17); adoption-roadmap B-bucket
Last Updated: 2026-06-17
