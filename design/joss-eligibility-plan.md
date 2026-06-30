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

## Part D — Submission-path strategy: JOSS-first, arXiv deferred (session 11)

**Context.** Community consensus (independent-researcher arXiv-endorsement threads,
e.g. r/AskPhysics) is blunt: arXiv endorsement is the wrong *first* step. The right
order is (1) situate the work in existing literature, (2) seek feedback from related
researchers — ideally face-to-face / coalition-building, not cold endorsement
requests, (3) go through journal peer review (no endorsement needed; passing it makes
arXiv endorsement trivial), (4) endorsement / arXiv last.

**Why this validates the existing plan.** sci-adk's primary venue is already JOSS — a
peer-reviewed journal. The consensus therefore *supports* the current track; arXiv was
only ever the optional visibility play, never the gate.

**sci-adk is not the cautionary case.** Unlike an unaffiliated theory manuscript of
doubtful substance, sci-adk is a working tool with a public repo, a large automated
test suite, demonstrated runs, and a `verify` reproducibility property — a
peer-reviewable artifact with prior-work / novelty positioning built in.

**The convergence that matters.** JOSS's open review *is* the community-feedback step the
consensus recommends, and JOSS reviewers run the tool — which is itself external-use
evidence. So "engage real users / get community feedback" (Part C, P0-2) and "go through
journal review" (this section) are the *same* action, with three payoffs at once: correct
scientific procedure + P0-2 evidence + eventual trivial endorsement.

**Decisions.**
- [DECISION] **arXiv is deprioritized to post-JOSS / optional.** Do NOT pursue arXiv
  endorsement as a near-term step. The thicker `paper/methods-arxiv.md` (+ `.tex`) is not
  wasted: it serves as outreach material (share with related researchers for feedback) and
  can go to arXiv later — after JOSS acceptance, via an institutional-email endorsement path,
  or not at all. (Eligibility itself is fine: it is an original systems/methods paper, exempt
  from the CS review-paper ban — see the methods DRAFT banner.)
- [DECISION] **Primary effort = JOSS + genuine engagement** (Part C), which is the right
  procedure *and* the P0-2 unblock.
- [OPEN — author] **Affiliation.** The manuscripts say "Independent Researcher," but the
  author holds a University-of-Seoul affiliation. An institutional email would (a) largely
  dissolve any arXiv-endorsement friction and (b) place the author outside the
  unaffiliated-submitter scrutiny bucket. Confirm whether "Independent Researcher" is the
  intended framing or whether the institutional affiliation should appear (also a DRAFT-banner
  item).
- [GUARDRAIL] **AI-assistance reputational risk.** Heavy disclosed AI assistance invites the
  "LLM-generated" suspicion the community flags. Manage it by keeping the AI-usage disclosure
  and by demonstrating genuine author ownership / understanding in any outreach or review
  exchange — never abstract hand-waving or "delegated to others" phrasing.

---

Version: 1.1
Source: sci-adk session 10 — first-review triage (manuscript passed; repo gate
identified). Measured 2026-06-30. Part D added session 11 (2026-06-30): JOSS-first /
arXiv-deferred submission-path strategy after community-consensus review.
Status: Active until JOSS submission (~2026-12).
