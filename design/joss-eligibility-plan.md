# JOSS Eligibility Plan (repo track to submission)

> Purpose: track the **repo-side** gate to JOSS submission. The manuscript
> (`paper/paper.md`) reached review-passing shape over review rounds 1-3; what
> now determines accept/reject is no longer the manuscript but two time-gated
> repository properties JOSS screens for. This document is the single source for
> that track. Covers **P0-1** (six-month public development history / cadence)
> and **P0-2** (external use / community engagement for a solo author).
>
> Companion: `paper/paper.md` (manuscript), `design/release-readiness.md`
> (G-D/G-B gates), memory `[[project_research-roadmap-and-joss]]` (venue=JOSS,
> no-APC, timeline).

---

## Status snapshot (measured 2026-06-30)

| Property | Measured | Gate |
|----------|----------|------|
| Repo visibility / created | `ccy5123/sci-adk` PUBLIC, `2026-06-01` | 6-month mark ≈ **2026-12-01** |
| Public issues | 0 | P0-2 gap |
| Meaningful PRs | ~0 | P0-2 gap |
| Releases | v0.2.0 (1) | P0-1 evidence (good start) |
| Commit distribution | 13 in 2026-05, **113 in 2026-06** | P0-1 burst risk |
| Community files | README, CONTRIBUTING, LICENSE (MIT), CITATION.cff | present |

Already done: MIT LICENSE, CITATION.cff, CONTRIBUTING.md, README adoption pass
(version/test-count sync, external-use framing, Support section), v0.2.0 release,
manuscript + verified bib.

---

## Part B — P0-1: six-month public history (cadence)

**JOSS rule (2025):** a project must show ~6 months of public development history
(releases, public issues, PRs) before submission. Screening flags repos made
public just before submission, and commit history crammed into a short window.

**Implication for us:** the 6-month clock runs `2026-06-01 -> ~2026-12-01`. This
is *why* the repo is at v0.2.0, not v1.0.0. The live risk is not the calendar but
the **burst pattern** (113/126 commits in a single month). A reviewer reads steady,
spread activity as "sustained development"; a June spike then silence reads as
"generated, then parked."

**Plan (ordering, not effort estimates):**

1. **Spread activity across the window.** Land small, real commits / issues / PRs
   in each month from now to submission — not a second burst near December.
2. **Release as milestones land.** Cut v0.3.x, v0.4.x as features/fixes accrue;
   each tagged release is first-class history evidence.
3. **Keep changes substantive.** Doc-only churn to game the calendar is itself a
   flag; tie activity to genuine fixes (e.g., the quickstart defect below) and
   features.

> Verdict: P0-1 self-resolves with disciplined cadence. It is the *easy* gate.

---

## Part C — P0-2: external use / community engagement (solo author)

**JOSS rule:** solo author + zero external use/community evidence = "not
acceptable." Solo authorship is allowed, but external use, collaboration, or
community engagement must be the main signal, shown in the repo or paper.

**Implication:** this cannot be manufactured by writing more code. It needs *other
people* to run sci-adk and leave a trace. This is the genuinely hard, possibly
blocking gate.

**Plan:**

1. **Make the first five minutes work.** A fresh external user's first command must
   succeed cleanly.
   - [x] **RESOLVED (README, not a code bug).** The Quick Start now leads with
         `sci-adk verify runs/t1-godel` — the bundled run that re-verifies clean
         (REPRODUCED, exit 0), which is also sci-adk's core property. Diagnosis
         correction (measured): `sci-adk run --t1-demo` halting under the default
         guards is *intended* strict-science behavior (the bare demo carries no
         negative control by design, G3) — the old Quick Start oversold it as a
         clean verdict. `--no-strict-science` is documented for a quick smoke run.
         No src change; strict/lenient behavior is already covered by tests
         (test_science_guards, test_capability_registry).
   - [ ] README install + example verified by someone who is not the author.
2. **Recruit >= 1 external user.** A colleague, lab member, or someone from the
   computational/mathematical-chemistry community runs a real (small) study and
   leaves a trace — ideally a GitHub issue (question, bug, or feedback).
3. **Issue tracker activity from real use.** Open issues that record genuine use
   and iteration, not self-dialogue. Public issues + their resolution are the
   strongest solo-author signal.
4. **(Optional) Announce to attract a user.** A short note / preprint / community
   post to surface sci-adk to potential users.

> Verdict: P0-2 does not self-resolve. The single highest-value action on the whole
> repo track is **one external user + a public issue trace** — it directly breaks
> P0-2 and incidentally feeds P0-1.

---

## Timeline (calendar milestones)

| Window | Focus |
|--------|-------|
| now -> Oct | Fix quickstart blocker; README verified by a non-author; spread cadence; recruit external user(s); v0.3.x release |
| Nov | T-1 dogfood to validate the 1.0 surface in real use; resolve open issues; confirm 6-month/public-history facts |
| ~Dec (submission) | Cut v1.0.0 tag + Zenodo archive (DOI) (G-D D2/D3); strip paper HTML comment; submit to JOSS |

---

## Honest fallback (P0-2 risk)

If, by ~November, external engagement is still zero, the honest options are:

- **(a) Delay submission.** Public-history evidence keeps accruing; no harm in waiting.
- **(b) Recruit a collaborator / co-author.** Dissolves the solo-author constraint directly.
- **(c) Reconsider venue.** If external use never materializes, JOSS may be the wrong fit.

Do not submit into a known P0-2 gap on the strength of a good manuscript — the
screening gate is explicit that it will desk-reject regardless of paper quality.

---

Version: 1.0
Source: sci-adk session 10 — first-review triage (manuscript passed; repo gate
identified). Measured 2026-06-30.
Status: Active until JOSS submission (~2026-12).
