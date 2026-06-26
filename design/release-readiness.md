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

## 3. G-A — Generalization validated (KEYSTONE)

The central design claim is a **domain-general** rigor kernel. That claim is
validated only when a 2nd domain plugs in **without a kernel edit**.

| # | Criterion | Status | Basis |
|---|-----------|--------|-------|
| A1 | A 2nd domain plugs into the kernel via the adapter seam with no kernel edit | `[OPEN]` | only T-1 adapter exists: `src/sci_adk/adapter/` = `t1_capability.py` + `t1_encoding.py`; the general contract is "validated only once a 2nd domain plugs in without a kernel edit" — `design/adoption-roadmap.md:134` |
| A2 | All in-repo runs are not a single domain family | `[OPEN]` | `runs/` = `t-1`, `t1-demo`, `t1-godel` — all T-1 (molecular) |
| A3 | Decide whether IEAM-P8 (ecotoxicology) satisfies A1 | `[TBD]` | IEAM-P8 used the operational/borrow path (in-session agent-authored experiments) in a separate workspace, not the in-repo capability-adapter seam; whether that counts as the formal gate is undecided. Resolve before claiming generalization |
| A4 | If A3 is "no", define what an in-repo T-2 adapter requires | `[OPEN]` | T-2 (p-adic similarity, empirical) is planned but research-gated — `design/session-5-handoff.md:85` ("사용자가 연구") |

Note: A1 and the paper's 2nd case study (T-2) are the **same work item** — one
2nd-domain pass discharges both. This is research-gated (the user supplies the
research).

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
| D1 | CLI/API surface frozen (semver 1.0 = stability promise) | `[OPEN]` | surface still growing — `package` / `pkgreqs` added recently |
| D2 | Version bump `0.1.0 -> 1.0.0` | `[OPEN]` | `pyproject.toml` = `0.1.0` |
| D3 | Git tag `v1.0.0` + GitHub release notes | `[OPEN]` | — |
| D4 | PyPI publish decision (publish vs source-only) | `[TBD]` | packaging metadata partial; decide scope |

## 7. G-E — Honesty / claims boundary (sci-adk's own principle, applied to itself)

| # | Criterion | Status | Basis |
|---|-----------|--------|-------|
| E1 | README/paper claims do not exceed validated evidence | `[OPEN]` | README/title assert "domain-general"; G-A not yet validated — either validate (G-A) or scope the claim down to "general seam, validated on T-1; 2nd domain in progress" |
| E2 | "record vs belief" applied to the release narrative | `[OPEN]` | the release is a Claim about sci-adk; it must cite its Evidence (validated domains) and not over-state |

## 8. Release sequence (gated by triggers, not dates)

1. **Resolve G-A (keystone).** Either confirm IEAM-P8 discharges the gate (A3),
   or run an in-repo T-2 adapter (A4). This single step validates the central
   claim *and* supplies the paper's 2nd case study.
2. **G-B** — write the methods paper on T-1 + T-2.
3. **G-C / G-D** — mechanical OSS hygiene + version bump + tag (parallelizable;
   safe to start once G-A has a plan).
4. **G-E** — final claims audit: every public assertion traces to validated
   evidence, or is scoped down.

## 9. Definition of Done (1.0 external)

All G-A..G-E items are `[DONE]`, **or** the public claims are explicitly scoped
down to exactly what is validated (an honest "validated on T-1; general seam
enforced; 2nd domain in progress" framing is a legitimate 1.0 — over-claiming
domain-generality on N=1 is not).

Until G-A is resolved, an external 1.0 that advertises domain-generality would
violate G-E and is **not** recommended.

---

Version: 0.1.0 (PLANNING RECORD)
Created: 2026-06-26
Related: `design/adoption-roadmap.md` (Stage 0 / generalization gate),
`design/sci-adk-productization-plan.md` (identity, deferred external release),
`design/session-5-handoff.md` (T-2 plan).
