# P0-2 — Ready-to-post submission texts

> Finalized copy for the pyOpenSci presubmission keystone and the repo "feedback
> wanted" issue. Operationalizes `p0-2-outreach-plan.md` §5 templates with the
> session decisions locked in: **affiliation = Independent Researcher**, **release =
> v0.3.0** (cut 2026-06-30), **test count = 1374** (CI py3.11/3.12), scope category
> named. The user posts these from their own account — posting is the keystone P0-2
> trace; it is not done here.
>
> Pre-flight status (p0-2-outreach-plan §4):
> - [x] Clean-clone first-run verified by a fresh isolated venv from the GitHub repo
>       (`git clone` → `pip install -e .` → `sci-adk verify runs/t1-godel` → exit 0,
>       Python 3.12.3, 2026-06-30). A non-author still needs to confirm independently.
> - [x] Tutorial is the landing page (`docs/tutorial.md`).
> - [x] v0.3.0 cut + GitHub release published.
> - [ ] Pinned "Feedback wanted" issue — text below; user posts.
> - [x] Affiliation framing confirmed: Independent Researcher.

---

## 1. pyOpenSci presubmission inquiry

**Where:** new GitHub issue at <https://github.com/pyOpenSci/software-submission/issues>
(presubmission-inquiry template if offered).
**Scope basis (confirmed against pyopensci.org/software-peer-review/about/package-scope):**
fits **"workflow automation and versioning"** — software that supports reproducible
workflows. Substantial-effort bar (~1000+ LOC, ~3 months) is far exceeded.

**Title:**

```
Presubmission inquiry: sci-adk — a rigor/verification kit for agent-assisted research
```

**Body:**

> Hi pyOpenSci team — I'd like to check whether **sci-adk** is in scope for review.
>
> **What it is:** a Python command-line research compiler built on a domain-general
> rigor/verification kernel. It keeps an append-only *record* (Evidence) separate from
> revisable *belief* (Claims); a deterministic, rule-based engine — **no LLM in the
> loop** — re-derives each claim's verdict from the recorded evidence, so a third party
> can run `sci-adk verify` **offline** and reproduce the verdict (plus a SHA-256 record
> digest as tamper-evidence). Repo: <https://github.com/ccy5123/sci-adk>
>
> **Why I think it supports scientific inquiry:** it targets a specific failure mode in
> agent-assisted research — conflating "the code ran" with "the claim is supported." By
> separating the evidence record from revisable claims and re-deriving each verdict
> deterministically, it makes an AI-assisted result *auditable* rather than taken on
> trust. I believe it fits the **"workflow automation and versioning"** scope category
> (reproducible workflows).
>
> **Status:** MIT-licensed, **1374 tests** in CI (Python 3.11 / 3.12), README +
> CONTRIBUTING + CITATION.cff + code of conduct, a 15-minute try-it tutorial
> (`docs/tutorial.md`), latest release v0.3.0. A clean-clone first run
> (`git clone` → `pip install -e .` → `sci-adk verify runs/t1-godel`) reproduces the
> bundled example offline, exit 0.
>
> **AI disclosure:** I'm an independent researcher and I developed this with substantial
> AI assistance under a human verification gate; I'm responsible for all content. The
> tool is itself partly a response to AI-slop-in-science — its verdict path is LLM-free
> and re-runnable by anyone.
>
> Is this in scope? Happy to adjust packaging to your checklist. Thanks!

---

## 2. Pinned "Feedback wanted" issue (sci-adk repo)

**Where:** new issue on <https://github.com/ccy5123/sci-adk/issues>, then **Pin** it.

**Title:**

```
Feedback wanted — try sci-adk and tell me where it breaks
```

**Body:**

> If you ran sci-adk — even just the 60-second check:
>
> ```bash
> git clone https://github.com/ccy5123/sci-adk && cd sci-adk
> pip install -e .
> sci-adk verify runs/t1-godel    # deterministic, offline, no LLM; exit 0 if it reproduces
> ```
>
> — I'd love to hear: what you ran, what you expected, what happened, and whether the
> **record / belief** split (append-only evidence vs revisable claims) is useful in your
> work. Bugs, confusion, and "this doesn't fit my case" are all exactly what I want.
>
> A specific question I'm chewing on: is scoping `sci-adk verify` to **internal
> consistency** (does the recorded evidence satisfy the pre-registered decision rules?)
> rather than *validity* the right call?
>
> 15-minute walkthrough: [`docs/tutorial.md`](https://github.com/ccy5123/sci-adk/blob/master/docs/tutorial.md).

---

## 3. After posting (do not skip)

- **Respond fast and substantively** to every comment/issue — this is the make-or-break
  P0-2 behavior (demonstrates genuine ownership, the anti-"delegated" signal).
- Log honestly in `p0-2-outreach-plan.md` §6 what was tried and what landed; count
  distinct non-author participants. P0-2 clears at **≥1 genuine external user with a
  public issue, OR pyOpenSci review underway**.
- Amplification (Mastodon/RSE Slack probe, then wider) comes *after* the message lands
  and a non-author confirms the first run — see `p0-2-outreach-plan.md` §2.
