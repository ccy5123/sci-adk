---
title: 'sci-adk: a rigor / verification Agentic Discovery Kit that separates the research record from belief'
tags:
  - Python
  - reproducibility
  - scientific workflow
  - agentic AI
  - verification
  - provenance
authors:
  - name: Chan Young Joe
    orcid: 0009-0007-5822-6714
    affiliation: 1
affiliations:
  - name: Independent Researcher, Republic of Korea
    index: 1
date: 26 June 2026
bibliography: paper.bib
---

<!--
JOSS draft (G-B, sci-adk session 9). Format verified 2026-06-26
(joss.readthedocs.io/en/latest/submitting.html + /paper.html): Markdown,
750-1750 words. The tagged release + Zenodo/figshare DOI is required AT
ACCEPTANCE, not submission -- so the v1.0.0 tag (release-readiness G-D D2/D3)
is the JOSS acceptance step.

Honesty boundary (G-E; design/g-a-a3-decision.md): claim a domain-general
*verification* kernel validated on a 2nd domain for VERIFICATION; do NOT claim
a cross-domain-validated autonomous-experiment *system*.

All sections drafted; paper.bib metadata verified 2026-06-26 against the arXiv
abstract pages. Before submission: confirm the GitHub repo is public, then (at
JOSS acceptance) make the v1.0.0 tagged release + Zenodo archive (G-D D2/D3).
-->

# Summary

sci-adk is an Agentic Discovery Kit (ADK): a research compiler that consumes a
structured research proposal and emits a paper draft, working code, and an
evidence trail, under a discipline that separates the **record** from **belief**.
The record is a monotone, append-only log of what happened — including null and
negative results. Belief is a non-monotone, revisable confidence (a `Claim`)
derived from that record; a supported claim can be demoted, marked contested, or
retracted as new evidence arrives. Agents propose; a deterministic, rule-based
engine judges by frozen criteria. A single command, `sci-adk verify`, re-applies
those criteria to the recorded evidence and is the sole verdict path — there is
no self-certification by the agent that produced the work. Each run leaves a typed
directory (`runs/<id>/`: a frozen `spec.json`, an append-only `evidence/` log,
derived `claims/`, checkpoints, and a rendered `paper/`) that a third party can
re-verify offline, without re-running the experiment and without a language model
in the loop.

# Statement of need

Agentic AI systems increasingly carry out research steps autonomously — searching
literature, running computations, and drafting conclusions. In doing so they
inherit a software-engineering assumption that is wrong for science: that a single
monotone, binary, terminal signal ("the build passes") equals truth. An agent that
both performs and certifies its own work has no independent check, and a fluent
narrative can outrun its evidence. sci-adk addresses this by making the verdict
deterministic, rule-based, and **external to the agent**. Each `Spec` pre-registers
its own `DecisionRule` per hypothesis, and a `Claim`'s status is judged against
*that* rule rather than a global threshold; there are no hard-coded success
metrics. Null and negative results are first-class outcomes recorded in the same
log, not failures to be hidden or retried away. The tool is aimed at individual
researchers and small groups who want agent assistance without surrendering the
integrity of the record — for example, a program of work applying advanced
mathematics (number theory, category theory, optimal transport) to computational
chemistry, where each result must remain independently checkable.

# State of the field

Recent systems bind agent outputs to evidence and audit agent-produced research,
and a growing literature critiques fully-autonomous "AI scientist" pipelines that
let a model both generate and judge results [@evibound; @aar; @aiscientist].
sci-adk's distinguishing commitment is architectural: the record/belief split is a
first-class type discipline, and a deterministic verification gate is the *only*
path to a verdict. The engine never asks a language model whether a claim holds; it
re-derives belief from the recorded evidence by the spec's frozen decision rule.

# Software design

The rigor **kernel** carries zero domain knowledge. `sci_adk.core` defines the
`Spec`, `Evidence`, and `Claim` types; `sci_adk.loop` holds the `DecisionEngine`
and the read-only `verify` audit; `sci_adk.render` is a pure, side-effect-free
renderer from the record to LaTeX. Domain content lives only in a **capability
adapter**, and the kernel never imports it — a one-way `adapter -> kernel`
dependency enforced on every test run by an abstract-syntax-tree lint, so a kernel
module that grows a domain import fails the build. The public surface is a curated
Python API (the record/belief types plus the verdict entry points) and a
command-line interface: `run` and its decomposed stage verbs (`init-spec`,
`amend-spec`, `execute`, `append-evidence`, `derive-claim`, `render`), the
verdict verbs (`verify`, `resolve`, `prior-work`, `novelty`, `contested`,
`status`), and publishing verbs that assemble a near-submission package and check
it against a frozen requirements contract. The implementation is Python, with an
extensive automated test suite run in continuous integration on Python 3.11 and
3.12. The `verify` audit reports, per recorded claim, whether it reproduces,
diverges, or remains unresolved under the frozen rules, and exits non-zero unless
every recorded claim reproduces — making the verdict scriptable in a reviewer's
own environment.

# Research impact

sci-adk has been exercised end-to-end on a first domain: T-1, a number-theoretic
("Gödel-style") molecular numbering scheme, compiled from proposal to a verifiable
paper draft. The **verification kernel** has additionally been run, unmodified and
with zero kernel edits, on a second and different domain — environmental
toxicology — evidencing the domain-general *verification* claim; that cross-domain
record is separate research with a paper in preparation. The autonomous experiment
adapter-seam, by contrast, is exercised on T-1 only and is not claimed here as
cross-domain. By keeping the verdict path deterministic and external, sci-adk lets
a single researcher run agent-assisted studies whose every claim cites its evidence
and can be re-verified by a reviewer offline — the property a credible research
record requires. The publishing verbs assemble that record into a self-contained
near-submission package whose integrity is checked against a frozen contract, so
the artifact a reviewer receives is the artifact the engine verified.

# AI usage disclosure

sci-adk's source code and this paper were developed with substantial AI assistance
(agentic coding and drafting with large language models) under a human verification
gate: every change and claim was reviewed and accepted by the author, who is
responsible for all content, and the automated test suite is the acceptance check
for the software.

# Acknowledgements

The author carried out this work as independent research with no specific grant
funding.

# References
