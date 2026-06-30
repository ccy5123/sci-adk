---
title: 'sci-adk: an Agentic Discovery Kit that separates the research record from belief'
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
JOSS draft (G-B, sci-adk session 9; revised session 10 after first review).
Format verified 2026-06-26 (joss.readthedocs.io/en/latest/submitting.html +
/paper.html): Markdown, 750-1750 words. The tagged release + Zenodo/figshare DOI
is required AT ACCEPTANCE, not submission -- so the v1.0.0 tag (release-readiness
G-D D2/D3) is the JOSS acceptance step.

Honesty boundary (G-E; design/g-a-a3-decision.md): claim a domain-general
*verification* kernel validated on a 2nd domain for VERIFICATION; do NOT claim
a cross-domain-validated autonomous-experiment *system*.

Session-10 review incorporated: lead with concrete/testable properties (offline
LLM-free re-verify; machine-enforced boundary); make the spec-freeze->digest->
boundary-guard ordering explicit (verdict independence is auditable, not just
asserted); scope `verify` to internal consistency, not validity; expand State of
the field with workflow/provenance software comparison + TMS/PROV/pre-reg lineage;
state T-1 is independently motivated, not a demo built to drive the tool; rest the
generality claim on the machine-enforced boundary, not the in-prep 2nd-domain paper.

SUBMISSION TODO: (1) strip this comment; (2) verify+enrich every paper.bib entry
with DOIs against the source pages (the new lineage/software refs were added with
author/year/venue at high confidence; DOIs/pages to be confirmed at submission);
(3) confirm the repo is public with >=6 months of open-development history and
that "Independent Researcher / no specific grant funding" is literally accurate;
(4) at acceptance, cut the v1.0.0 tagged release + Zenodo archive (G-D D2/D3).
-->

# Summary

sci-adk is a command-line research compiler: it takes a structured research
proposal and emits a paper draft, working code, and an evidence trail, with one
property unusual for an agent-assisted tool — the verdict on whether a result
holds is produced by a deterministic, rule-based engine that runs **with no
language model in the loop**, and a third party can re-run that verdict offline. A
single command, `sci-adk verify`, re-applies each hypothesis's pre-registered
decision rule to the recorded evidence and exits non-zero unless every recorded
claim reproduces, so the check is scriptable in a reviewer's own environment with
no API calls.

That design rests on separating the research **record** from **belief**. The
record is a monotone, append-only log of what happened — it only ever grows, never
retracting — including null and negative results. Belief — a `Claim` — is a
non-monotone, revisable confidence derived from that record; a supported claim can
be demoted, marked contested, or retracted as new evidence arrives. Agents propose; the engine judges by frozen
criteria, and there is no self-certification by the agent that produced the work.
Each run leaves a typed directory (`runs/<id>/`: a frozen `spec.json`, an
append-only `evidence/` log, derived `claims/`, checkpoints, and a rendered
`paper/`) that a third party can re-verify without re-running the experiment.

# Statement of need

Agentic AI systems increasingly carry out research steps autonomously — searching
literature, running computations, and drafting conclusions. The risk this
introduces is not that builds pass spuriously but that **the agent that performs
the work also certifies it**: with no independent check, a fluent narrative can
outrun its evidence, and a system can report success by the only standard it sets
for itself. sci-adk makes the verdict deterministic, rule-based, and **external to
the agent**. Each `Spec` pre-registers its own `DecisionRule` per hypothesis,
frozen before execution, and a `Claim`'s status is judged against *that* rule
rather than a global threshold; there are no hard-coded success metrics to game.
Null and negative results are first-class outcomes recorded in the same log, not
failures to be hidden or retried away.

The tool is aimed at individual researchers and small groups who want agent
assistance without surrendering the integrity of the record — for example, a
program applying advanced mathematics (number theory, category theory, optimal
transport) to computational chemistry, where each result must remain
independently checkable.

# State of the field

Workflow- and provenance-tracking tools already record *how* a result was
produced: Snakemake and comparable engines capture computational workflows
[@snakemake], DVC versions data and pipelines, and Sumatra and ReproZip capture
execution provenance [@sumatra; @reprozip]. sci-adk reuses rather than replaces
this layer — a run directory is git-tracked provenance — and adds the part those
tools deliberately leave to the researcher: a typed, revisable **belief** state
and a deterministic gate that decides whether a recorded claim is *currently*
supported. Its record/belief discipline has clear antecedents — justification- and
assumption-based truth-maintenance systems [@doyle; @dekleer], the W3C PROV
provenance model [@prov], pre-registration in the empirical sciences [@prereg],
and event sourcing in software architecture — and sci-adk's contribution is to
compose them into a first-class type discipline in which a deterministic
verification gate, never a language model, is the *only* path to a verdict. A
separate line of work binds agent outputs to evidence, audits agent-produced
research, and critiques pipelines that let a model both generate and judge results
[@evibound; @aar; @aiscientist]; sci-adk's distinguishing commitment is
architectural rather than a post-hoc audit.

# Software design

The rigor **kernel** carries no domain knowledge. `sci_adk.core` defines the
`Spec`, `Evidence`, and `Claim` types; `sci_adk.loop` holds the `DecisionEngine`
and the read-only `verify` audit; `sci_adk.render` is a pure, side-effect-free
renderer from the record to LaTeX. Domain content lives only in a **capability
adapter**, and the kernel never imports it — a one-way `adapter -> kernel`
dependency enforced on every test run by an abstract-syntax-tree import lint, so a
kernel module that grows a domain import fails the build. The lint checks imports,
not logic; it is a necessary, machine-checked boundary, not a proof that no domain
assumption can enter by any other route.

The verdict's independence rests on an ordering the tool makes checkable, and the
paper is precise about what that buys. `spec.json` — and with it every
`DecisionRule` — is authored and frozen as the first stage, before any evidence is
appended, so within a run the rule cannot be rewritten to fit the evidence after
the fact. Independently, the record carries a SHA-256 digest over the canonical
`spec.json` plus the sorted evidence and verdict logs, which `verify` re-checks, so
a reviewer can confirm the audited record was not altered. These are distinct
guarantees — staging order gives intra-run precedence, the digest gives
tamper-evidence — and neither is a trusted wall-clock timestamp: like
pre-registration, the discipline assumes the spec was committed in good faith and
does not, by itself, stop an operator from discarding a run and re-specifying
against what they saw. A hard temporal guarantee would require committing the spec
to an external, timestamped store before execution.

The public surface is a curated Python API (the record/belief types plus the
verdict entry points) and a command-line interface: `run` and its decomposed stage
verbs (`init-spec`, `amend-spec`, `execute`, `append-evidence`, `derive-claim`,
`render`), the verdict verbs (`verify`, `resolve`, `prior-work`, `novelty`,
`contested`, `status`), and publishing verbs that assemble a near-submission
package and check it against a frozen requirements contract. The implementation is
Python, with an extensive automated test suite run in continuous integration on
Python 3.11 and 3.12. The `verify` audit reports, per recorded claim, whether it
reproduces, diverges, or remains unresolved under the frozen rules, and exits
non-zero unless every recorded claim reproduces.

# Research impact

`verify` audits *internal consistency* — whether the recorded evidence satisfies
the rules pre-registered for it — not the scientific validity of the experiment
behind that evidence. sci-adk makes a research record auditable and re-checkable
and is explicit that this is necessary, not sufficient, for a result to be true.
Within that scope it has been exercised end-to-end on a first domain: T-1, a
number-theoretic ("Gödel-style") molecular numbering scheme — an independently
motivated problem from the author's mathematics-to-chemistry program (its
mathematical write-up in preparation), not a demonstration built to drive the
tool; the compiled T-1 run ships in the repository and passes `verify`. The
**verification kernel** has additionally been run, unmodified and with zero kernel
edits, on a second and different domain — environmental toxicology; the basis for
the domain-general *verification* claim is the machine-enforced kernel/adapter
boundary described above, with that second study (paper in preparation) as
corroboration rather than proof. The autonomous experiment adapter-seam, by
contrast, is exercised on T-1 only and is not claimed here as cross-domain. By
keeping the verdict path deterministic and external, sci-adk lets a single
researcher run agent-assisted studies whose every claim cites its evidence and can
be re-verified by a reviewer offline. The publishing verbs assemble that record
into a self-contained near-submission package whose integrity is checked against a
frozen contract, so the artifact a reviewer receives is the artifact the engine
verified.

# AI usage disclosure

sci-adk's source code and this paper were developed with substantial AI assistance
(agentic coding and drafting with large language models, via the MoAI-ADK agentic
development kit [@moaiadk]) under a human verification gate: every change and claim
was reviewed and accepted by the author, who is responsible for all content, and
the automated test suite is the acceptance check for the software.

# Acknowledgements

The author carried out this work as independent research with no specific grant
funding. sci-adk was developed using MoAI-ADK [@moaiadk], an agentic development
kit for Claude Code; its orchestrator-plus-specialist-plus-hook pattern also shaped
sci-adk's operational layer, which adopts that structure while repurposing its
deterministic gate from a software-build verdict to sci-adk's scientific
record/belief verdict.

# References
