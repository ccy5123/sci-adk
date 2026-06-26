# sci-adk 1.0 External Release Readiness

> Status: gating checklist for an external (OSS + methods paper) 1.0 release
> Created: 2026-06-26
> Classification: PLANNING RECORD (criteria, not a decision to release)

## 0. What this document is

A release-readiness bar for a **1.0 external public release** of sci-adk as an
OSS reference implementation plus a methods paper. It does **not** authorize a
release; it defines the criteria a release must meet and records the current
status of each, measured against the repository.

Status markers: `[DONE]` met · `[OPEN]` not yet met · `[TBD]` needs a judgment
call before it can be marked.

## 1. Decision context (read first)

An external release **reopens a deliberately deferred decision.** sci-adk's
locked identity is a *domain-general rigor/verification ADK (Agentic Discovery
Kit) for the user's own research — not an external shipping product; external
release is "deferred-not-foreclosed."* (Source: identity record in
`design/sci-adk-productization-plan.md` and the productization memory.)

Going to an external 1.0 is therefore not a version bump — it is a commitment to
publicly stand behind sci-adk's central claim. The honesty principle sci-adk
applies to research (record vs belief; never claim beyond the evidence) **applies
to its own release**: the release may not advertise more than is validated.

## 2. Gate classes

| Gate | Name | Keystone? |
|------|------|-----------|
| G-A | Generalization validated | YES — everything else is premature without it |
| G-B | Methods paper | depends on G-A (T-2 is its 2nd case study) |
| G-C | OSS release hygiene | mechanical, parallelizable |
| G-D | Versioning & API stability | semver 1.0 = stability commitment |
| G-E | Honesty / claims boundary | the release must not over-claim |

## 3. G-A — Generalization validated (KEYSTONE — substantively validated)

The central design claim is a **domain-general** rigor/verification kernel. A3 was
resolved on 2026-06-26 (`design/g-a-a3-decision.md`): A1 conflated two separable
claims and is **split**. The verification half (A1a) is **validated on a 2nd domain**
(IEAM-P8, ecotoxicology/DEB-TK); the autonomous experiment-seam half (A1b) is **scoped
out** of the 1.0 claim (the de-emphasized "player" half, T-1 only).

| # | Criterion | Status | Basis |
|---|-----------|--------|-------|
| A1a | A 2nd domain plugs into the kernel's **Verifier** interface (`DecisionEngine`/`sci-adk verify`) + typed Spec/Evidence/Claim store with no kernel edit | `[DONE]` | IEAM-P8 (`~/research/ieam-followup-p8`): 27 typed-store runs, `package/06_provenance/verify_all.txt` = "27/27 runs reproduce all recorded claims", 100 Claims (81/17/2), zero kernel edits — `design/g-a-a3-decision.md` §2.2 |
| A1b | A 2nd domain plugs into the **Experiment** adapter-registry (`ExperimentFn`/`--capability`) with no kernel edit | `[SCOPED OUT]` | only the T-1 capability is registered (`src/sci_adk/adapter/registry.py` + `t1_capability.py`); IEAM-P8 used the sanctioned operational/borrow path (A5), not the registry. De-emphasized player half — not advertised in the 1.0 claim, not a blocker — `design/g-a-a3-decision.md` §3 |
| A2 | All in-repo runs are not a single domain family | `[OPEN]` (cosmetic) | in-repo `runs/` = `t-1`, `t1-demo`, `t1-godel` — all T-1; the 2nd-domain validation is **external** (IEAM-P8). An in-repo T-2 run would close this cosmetically but adds no new validation beyond A1a |
| A3 | Decide whether IEAM-P8 (ecotoxicology) satisfies A1 | `[DONE]` | Resolved: discharges A1a (verification generality), not A1b (experiment seam) — full record in `design/g-a-a3-decision.md` |
| A4 | If A1b is pursued, define what an in-repo T-2 adapter requires (`t2_*` provider + registry entry + `checkpoint_loop` path) | `[OPEN]` (optional) | needed only to validate A1b; under the A3 verdict A1b is scoped out, so A4 is future/optional, not a 1.0 blocker — T-2 (p-adic similarity) is research-gated, `design/session-5-handoff.md:85` |

Note: the paper's 2nd case study (G-B B3) is a **separate question** from A1b. IEAM-P8
serves as the cross-domain **verification** evidence (A1a); the methods paper's primary
case study remains T-1. Producing a paper-grade T-2 writeup is G-B work, not required to
discharge the G-A keystone.

## 4. G-B — Methods paper

Publication plan = Option 4 (methods paper + T-1/T-2 case studies). (Source:
publication-plan memory; Phase 0 / MIT license already done.)

| # | Criterion | Status | Basis |
|---|-----------|--------|-------|
| B1 | Paper drafted (methods + both case studies) | `[OPEN]` | no manuscript in repo |
| B2 | T-1 case study writeup | `[OPEN]` | `runs/t1-godel/paper/` has a draft; needs paper-grade writeup |
| B3 | T-2 case study writeup | `[OPEN]` | == G-A A1/A4 (research-gated) |
| B4 | Render + publishing pipeline exists | `[DONE]` | render reframe + publishing F1/F2/F3 + package layer on master |
| B5 | CITATION.cff present and consistent with the paper | `[OPEN]` | software `CITATION.cff` added (G-C/C7); paper-citation consistency still pending the paper itself |

## 5. G-C — OSS release hygiene

| # | File / item | Status | Basis |
|---|-------------|--------|-------|
| C1 | `LICENSE` (MIT) | `[DONE]` | `LICENSE` present; `pyproject.toml` `license = { text = "MIT" }` |
| C2 | `README.md` current | `[DONE]` | refreshed 2026-06-25 (commit `43408b5`) |
| C3 | `CONTRIBUTING.md` | `[DONE]` | added; grounded in the rigor discipline + F4 kernel/adapter seam + tool policy |
| C4 | `CODE_OF_CONDUCT.md` | `[DONE]` | Contributor Covenant 2.1; contact ccy5123ccy@gmail.com |
| C5 | `CHANGELOG.md` | `[DONE]` | Keep a Changelog; accumulated history under `[Unreleased]` |
| C6 | `SECURITY.md` | `[DONE]` | private reporting + Docker code-execution scope note |
| C7 | `CITATION.cff` | `[DONE]` | CFF 1.2.0; Chan Young Joe, ORCID 0009-0007-5822-6714 |
| C8 | CI (`.github/workflows/`) running the suite on push/PR | `[DONE]` | `.github/workflows/ci.yml`; py3.11 + 3.12; green on push (1266 passed, 15 integration deselected -- Docker-path tests marked `integration` so the unit lane is hermetic) |
| C9 | `pyproject` metadata: `[project.urls]`, description aligned to ADK framing | `[DONE]` | ADK-framed description + `authors` + classifiers + `[project.urls]` + `[dev]` extra (pytest) |

## 6. G-D — Versioning & API stability

| # | Criterion | Status | Basis |
|---|-----------|--------|-------|
| D1 | CLI/API surface frozen (semver 1.0 = stability promise) | `[OPEN]` (contract decided) | surface measured + fixed as a contract in `design/surface-freeze-analysis.md` (17 verbs / 83 flags; stopped growing at HEAD-1, `6e96103`; scope = CLI + curated Python API; publishing layer `package`/`pkgreqs`/`pubreqs` included). Closes on the D1 execution step: curated `__all__` in `src/sci_adk/__init__.py` + version bump |
| D2 | Version bump `0.1.0 -> 1.0.0` | `[OPEN]` | `pyproject.toml` = `0.1.0` |
| D3 | Git tag `v1.0.0` + GitHub release notes | `[OPEN]` | — |
| D4 | PyPI publish decision (publish vs source-only) | `[TBD]` | packaging metadata partial; decide scope |

## 7. G-E — Honesty / claims boundary (sci-adk's own principle, applied to itself)

| # | Criterion | Status | Basis |
|---|-----------|--------|-------|
| E1 | README/paper claims do not exceed validated evidence | `[DONE]` | applied 2026-06-26: headline surfaces (README:9, pyproject:8, CITATION:5) now claim a domain-general **kernel** (structural, always true) + capability-adapter seam — not a cross-domain-validated "system". 2nd-domain *verification* validation stated honestly in README Remaining as separate research (paper in preparation); the autonomous experiment seam (A1b) is not advertised |
| E2 | "record vs belief" applied to the release narrative | `[DONE]` | the release Claim cites its Evidence: in-repo T-1 (visible) + the verification kernel run on a 2nd domain (IEAM-P8, external/paper-pending), stated as such; nothing claimed beyond `design/g-a-a3-decision.md` |

### G-E audit (2026-06-26) — findings + wording, **APPLIED 2026-06-26 (post-G-A)**

Audit of every public surface for "domain-general" asserted as a *validated*
property. **Applied** after the A3 verdict (`design/g-a-a3-decision.md`): the
headline surfaces were scoped to a domain-general **kernel** (structural fact);
the 2nd-domain *verification* validation is stated in README Remaining as separate
research (paper in preparation), and the autonomous experiment seam (A1b) is not
advertised. The chosen honesty level was **structural/conservative** (user decision
2026-06-26): private IEAM-P8 evidence is not put forward as a headline claim, per
sci-adk's own "a Claim must cite its Evidence" principle. Original findings retained
below for the record.

Over-claim sites (assert generality as fact):
- `README.md:9` (identity line) — "a **domain-general** rigor / verification system"
- `pyproject.toml:8` (description) — "a **domain-general** rigor / verification system"
- `CITATION.cff:5` (abstract) — "A **domain-general** rigor / verification ADK"

Tension: `README.md:238` (Remaining) already states generality is "validated only
once a second domain plugs in without a kernel edit" (G-A). So line 9 (fact) vs
line 238 (not-yet-validated) is an internal contradiction. NOT an over-claim:
`README.md:230` figure "domain-general" = the structural fact that the kernel
carries zero domain code — keep.

Prepared honest wording (correct under either G-A outcome — design is general now;
cross-domain *validation* is what G-A supplies):
- README:9 → "a rigor / verification system built on a **domain-general kernel**
  (zero domain code) and a capability-adapter seam ... validated end-to-end on
  T-1; cross-domain generalization is the open gate (see Remaining)."
- pyproject:8 → "...a rigor / verification system with a **domain-general kernel +
  capability-adapter seam** -- 4-pane proposal to paper + code + an evidence trail..."
- CITATION:5 → "A rigor / verification ADK, **built on a domain-general kernel and
  a capability-adapter seam**, that keeps an append-only record ..."

If G-A validates a 2nd domain, the bare "domain-general" claim becomes evidence-
backed and the qualifier can be relaxed accordingly; if not, the qualified wording
is the honest end state.

## 8. Release sequence (gated by triggers, not dates)

1. **G-A (keystone) — RESOLVED 2026-06-26.** A3 verdict (`design/g-a-a3-decision.md`):
   A1a (verification-kernel generality) is validated on a 2nd domain (IEAM-P8); A1b
   (autonomous experiment seam) is scoped out of the 1.0 claim. The central
   *verification* claim is validated. Next step is the **G-E apply** (relax the
   "domain-general" wording to the evidence-backed verification framing).
2. **G-B** — write the methods paper (primary case study T-1; IEAM-P8 as cross-domain
   verification evidence; a paper-grade T-2 writeup is optional, not gating).
3. **G-C / G-D** — mechanical OSS hygiene + version bump + tag (parallelizable;
   safe to start once G-A has a plan).
4. **G-E** — final claims audit: every public assertion traces to validated
   evidence, or is scoped down.

## 9. Definition of Done (1.0 external)

All G-A..G-E items are `[DONE]`, **or** the public claims are explicitly scoped
down to exactly what is validated (an honest "validated on T-1; general seam
enforced; 2nd domain in progress" framing is a legitimate 1.0 — over-claiming
domain-generality on N=1 is not).

G-A is **resolved** (2026-06-26, `design/g-a-a3-decision.md`): the domain-general
*verification* claim is validated on a 2nd domain (IEAM-P8, ecotox), so an external
1.0 advertising **domain-general rigor/verification** no longer over-claims — provided
the wording is the verification framing (G-E apply step) and does not advertise the
autonomous experiment seam as cross-domain (A1b, scoped out). The remaining gates are
G-B (paper), G-C/G-D (hygiene/version, mechanical), and the G-E wording apply.

---

Version: 0.1.0 (PLANNING RECORD)
Created: 2026-06-26
Related: `design/adoption-roadmap.md` (Stage 0 / generalization gate),
`design/sci-adk-productization-plan.md` (identity, deferred external release),
`design/session-5-handoff.md` (T-2 plan).
