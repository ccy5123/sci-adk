# P0-2 Engagement / Outreach Execution Plan

> Operationalizes `joss-eligibility-plan.md` Part C (P0-2: external use / community
> engagement) and Part D (JOSS-first, arXiv deferred). Goal: get sci-adk genuinely
> used and critiqued by other people, leaving public traces — the one action that
> unblocks JOSS's solo-author screen. Target community (chosen): research-software /
> reproducibility. Style (chosen): public posting for fast exposure, built around a
> peer-review keystone.

---

## 0. The convergence (why one path serves three goals)

The Reddit-consensus "correct procedure" (situate in literature → get feedback from
related researchers → journal peer review → endorsement last) and sci-adk's P0-2
blocker and the JOSS submission are **the same path** if routed through software peer
review. Every reviewer who runs the tool and comments in a public issue is
simultaneously: community feedback, a P0-2 external-use trace, and a step toward
publication.

---

## 1. Keystone channel — pyOpenSci open peer review

**What it is.** pyOpenSci (pyopensci.org) runs open, transparent, supportive peer
review of **Python research software** by volunteer reviewers, conducted entirely in
public GitHub issues. 61 packages accepted to date.

**Why it is the keystone (triple win).**
- **Feedback / coalition** — exactly the "related researchers vet your work" the
  community consensus recommends, in a supportive (not hostile) software-focused venue
  where a working, tested tool is the asset.
- **P0-2 evidence** — the review happens in public GitHub issues; reviewers run the
  software and leave durable traces. This is the strongest possible external-use /
  community-engagement signal for JOSS's solo-author screen.
- **JOSS on-ramp** — pyOpenSci ↔ JOSS partnership: if accepted by pyOpenSci and in
  JOSS scope, **JOSS accepts the pyOpenSci review as its own and fast-tracks** (no
  second review). sci-adk already has `paper/paper.md` (the JOSS artifact). No arXiv,
  no endorsement involved.

**Scope caveat (handle honestly first).** pyOpenSci reviews "research software and
software that directly supports scientific inquiry." sci-adk plausibly fits, but DO
NOT assume — open a **presubmission inquiry** (pyOpenSci explicitly offers this) to
confirm scope and get editor feedback before a full submission. The presubmission
inquiry is itself a public issue = the first P0-2 trace.

**Concrete steps.**
1. Read pyOpenSci's peer-review scope + author guide (pyopensci.org/software-peer-review).
2. Run their packaging/readiness checklist against sci-adk (docs, tests, CI, packaging,
   contributing, license — sci-adk already has most: 1369 tests, README, tutorial,
   CONTRIBUTING, MIT, CITATION).
3. Open a **presubmission inquiry** at github.com/pyOpenSci/software-submission using
   the template (template 1, below). Honest framing; ask whether it is in scope.
4. If in scope → full submission; opt into the JOSS path (craft/confirm paper.md to
   JOSS standards — already drafted).

---

## 2. Amplification — public posting (the chosen fast-exposure layer)

Wrap the keystone with light public posting to surface a genuine *user* (beyond
reviewers) and broaden feedback. Every post drives to the **tutorial**
(`docs/tutorial.md`) and the **issue tracker**.

**Channels (research-software / reproducibility), fit + risk:**

| Channel | Fit | Note |
|---|---|---|
| pyOpenSci community (Slack/Discourse) | High | natural home; announce the presubmission |
| US-RSE / Society of RSE (Slack, newsletters) | High | active RSE communities; "built a tool, feedback?" is welcome |
| The Turing Way community (GitHub/Slack) | High | reproducible-research audience; record/belief resonates |
| Software Sustainability Institute (blog/community) | Medium-High | research-software audience; possible guest post |
| Mastodon (fosstodon.org) #ResearchSoftware #Reproducibility #RSE | Medium | fast, low-friction; good first probe |
| Reddit r/Python (Showcase), Hacker News (Show HN) | Medium | broad reach, **higher AI-slop scrutiny** — post only after messaging is validated and the clean-clone first-run is verified |

> Confirm current join links before posting (Slack invites rotate). Do not invent links.

**Sequencing (fast but not reckless):**
- Probe first in ONE low-risk venue (Mastodon/fosstodon + one RSE Slack), measure
  reaction, iterate the wording.
- Then widen (Turing Way, SSI, forums), then broad (r/Python / Show HN) only after the
  message lands and the first-run is verified by a non-author.

---

## 3. Messaging guardrails (invert the Reddit red flags)

The thread's suspicion signals, turned into rules. Heavy disclosed AI assistance makes
these non-negotiable for a public post.

- **Artifact-first, not claims-first.** Lead with a thing the reader verifies in 60s:
  `git clone … && sci-adk verify runs/t1-godel` → exit 0. Show, don't assert.
- **Specific and technical, never grandiose.** No "revolutionary/novel paradigm." State
  the concrete property (deterministic LLM-free verdict, re-runnable offline).
- **Situate in literature.** Name what it builds on (Snakemake/DVC, PROV, pre-registration,
  truth-maintenance) — exactly the State-of-field already in the paper. This is the single
  strongest anti-crackpot signal.
- **AI disclosure as a strength, not a liability.** Disclose AI-assisted development AND
  the human-verification gate. The tool itself is an answer to AI-slop-in-science (the
  verdict path is LLM-free) — say so; it reframes the AI question.
- **Ask a specific question, not "thoughts?"** e.g. "Does the record/belief separation
  hold up? Is scoping `verify` to internal-consistency-not-validity the right call? Would
  you use this in your workflow?"
- **Request use and critique, never endorsement or citation.** Cold endorsement/citation
  asks are the red flag; "please try it and tell me where it breaks" is the green flag.
- **Respond fast and substantively** to every issue/comment — demonstrates genuine
  ownership (the anti-"delegated-to-others" signal). This is the make-or-break behavior.
- **No overclaim on generality.** Domain-general *verification kernel* only; T-1 is an
  example. (Same honesty boundary as the papers.)

---

## 4. Pre-flight gates (before any public push)

- [ ] **Clean-clone first-run verified by a non-author** (P0-2 plan #1, still open). A
      stranger's first `pip install -e . && sci-adk verify runs/t1-godel` must succeed.
      A bad first impression in public is expensive — gate the push on this.
- [ ] Tutorial is the landing page for every link (done: `docs/tutorial.md`).
- [ ] Pinned "Feedback wanted" issue exists (template 3).
- [ ] (Recommended) cut a **v0.3.x release** as a "maintained, try-this" signal — also
      spreads P0-1 cadence.
- [ ] Confirm the "Independent Researcher" vs University-of-Seoul affiliation framing
      (institutional email also smooths any future arXiv path).

---

## 5. Ready-to-use templates

### Template 1 — pyOpenSci presubmission inquiry (GitHub issue)

> Title: Presubmission inquiry: sci-adk — a rigor/verification kit for agent-assisted research
>
> Hi pyOpenSci team — I'd like to check whether sci-adk is in scope for review.
>
> **What it is:** a Python command-line research compiler + a domain-general
> rigor/verification kernel. It keeps an append-only *record* (Evidence) separate from
> revisable *belief* (Claims); a deterministic, rule-based engine — no LLM in the loop —
> re-derives each claim's verdict, so a third party can re-run `sci-adk verify` offline
> and reproduce it. Repo: github.com/ccy5123/sci-adk.
>
> **Why I think it supports scientific inquiry:** [one or two concrete sentences].
> **Status:** MIT, 1369 tests in CI (Python 3.11/3.12), docs + 15-min tutorial.
> **AI disclosure:** developed with substantial AI assistance under a human verification
> gate; I'm responsible for all content.
>
> Is this in scope? Happy to adjust packaging to your checklist. Thanks!

### Template 2 — short public post (Mastodon / forum)

> Built a small open-source tool I'd like feedback on: **sci-adk** keeps an agent-assisted
> research run's *record* (append-only evidence) separate from *belief* (revisable claims),
> and makes the verdict deterministic and **LLM-free** — `sci-adk verify` re-derives every
> claim from the record, offline, exit 0 if it reproduces. Try the 60-second check:
> `git clone … && sci-adk verify runs/t1-godel`. Tutorial + issues: [links].
> Honest about limits (it checks internal consistency, not validity) and AI-assisted dev.
> Would this fit your reproducibility workflow — and where does it break? #ResearchSoftware #Reproducibility

### Template 3 — pinned "Feedback wanted" GitHub issue

> Title: Feedback wanted — try sci-adk and tell me where it breaks
>
> If you ran sci-adk (even just `sci-adk verify runs/t1-godel`), I'd love to hear:
> what you ran, what you expected, what happened, and whether the record/belief split
> is useful in your work. Bugs, confusion, and "this doesn't fit my case" are all
> exactly what I want. See the 15-minute tutorial: docs/tutorial.md.

---

## 6. Success metric (tie to P0-2)

- First public trace: pyOpenSci presubmission inquiry opened.
- Target: **≥1 genuine external user** runs sci-adk and leaves a public issue, AND/OR
  pyOpenSci review underway (reviewers running it). Either satisfies the P0-2 screen.
- Track count of distinct non-author participants (issues, review comments). Log honestly
  what was tried and what landed (no vanity inflation).

---

## 7. What stays deferred

- **arXiv** — post-JOSS / optional (Part D). The pyOpenSci → JOSS route makes a cold arXiv
  preprint unnecessary for credibility; the methods-arxiv draft remains outreach material.
- Broad/high-scrutiny channels (Show HN, large subreddits) — only after the message is
  validated and the clean-clone first-run is confirmed.

---

Version: 1.0
Source: sci-adk session 11 (2026-06-30). Channels verified via web (pyOpenSci open peer
review + JOSS partnership confirmed). Companion to `joss-eligibility-plan.md` Part C/D.
Status: Active — keystone = pyOpenSci presubmission inquiry.
