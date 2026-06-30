<!--
DRAFT — NOT SUBMISSION-READY.

Author review required before any posting:
- Confirm affiliation and funding statement are literally accurate.
- Verify all paper.bib DOIs against source pages before posting.
- arXiv first submission in cs.SE / cs.DL may require category endorsement [UNVERIFIED — author to confirm].
- Strip this comment block before submission.
-->

# A Deterministic, LLM-Free Verification Gate for Agentic Research Workflows: The Record/Belief Architecture of sci-adk

**Chan Young Joe**
Independent Researcher, Republic of Korea

---

*DRAFT — prepared for author review; not a final submission.*

---

## Abstract

Agentic AI systems increasingly carry out individual research steps — literature search, computation, and narrative drafting — but the system that performs the work typically also certifies it, with no independent check. A fluent narrative can therefore outrun its evidence, and the only standard applied is the one the agent sets for itself. We describe the design of sci-adk, a command-line research compiler whose core contribution is architectural: the verdict on whether a recorded result currently holds is produced by a deterministic, rule-based engine that contains no language model and can be re-run offline by a third party. The design rests on a strict separation of the research *record* — a monotone, append-only log that includes null and negative results as first-class entries — from *belief*, a non-monotone, revisable `Claim` state derived from that record by re-applying frozen, hypothesis-specific decision rules. The boundary between a domain-free rigor kernel and a domain-specific capability adapter is machine-enforced by an abstract-syntax-tree import lint on every test run, which prevents kernel modules from growing domain dependencies silently. Five spec-layer science guards check analyticity, test-power, falsifiability, mode-coherence, and claim-cost at spec-compile time, with no language model in the loop. A referent-typed evidence-validity gate blocks synthetic data from grounding an empirical belief. We describe what each mechanism precisely guarantees and what it does not, and illustrate the architecture end-to-end with T-1, a number-theoretic molecular encoding that is an independently motivated first-domain example.

---

## 1. Introduction

The prospect of AI-assisted scientific research has moved from speculation to practice. Systems such as The AI Scientist [@aiscientist] demonstrate that language models can propose hypotheses, run experiments, and draft papers in a single autonomous loop. The capability is real and the productivity gain is substantial. But that design contains a structural vulnerability: the agent that produces a claim is the same agent that assesses whether the claim holds, and the assessment is expressed in the same medium — natural language — as the claim itself. There is no independent check; a confident, well-formed narrative is indistinguishable, from the outside, from a well-evidenced one.

This is not merely a theoretical concern. A separate line of work has identified and studied the problem: evidence-binding frameworks [@evibound] propose governance structures that require agents to cite evidence for every claim; claim-level auditability work [@aar] argues that deep research agents should produce auditable reasoning traces rather than opaque conclusions. These proposals share a common diagnosis — the agent should not be the sole arbiter of its own output — but they address it primarily through post-hoc audit and governance.

sci-adk's approach is architectural rather than post-hoc. The verdict is not a language model's assessment of the evidence; it is the output of a deterministic function that re-applies pre-registered, frozen decision rules to the recorded evidence log. That function contains no language model, runs on stored JSON, and exits with a numeric status code. A reviewer can clone the repository, install the package, run `sci-adk verify`, and obtain the same verdict without an API key or network connection.

The contribution is not a new kind of science. The tool's scope is explicitly *internal consistency*: does the recorded evidence satisfy the rules the researcher pre-registered for it? This is necessary but not sufficient for a result to be scientifically true. What sci-adk adds is a checkable, tamper-evident record and an unambiguous answer to the consistency question — properties that agentic workflows currently lack.

The remainder of the paper is structured as follows. Section 2 introduces the record/belief separation and the three core types. Section 3 describes the verification gate and what it precisely guarantees. Section 4 analyzes verdict independence: what the spec-freeze and record-digest mechanisms buy and where each stops. Section 5 describes the kernel/adapter seam and its machine enforcement. Section 6 covers the spec-layer science guards and the referent-typed evidence-validity gate. Section 7 situates sci-adk in the related-work landscape. Section 8 illustrates the architecture with the bundled T-1 worked example. Section 9 collects the honesty boundaries explicitly. Section 10 concludes.

---

## 2. The Record/Belief Separation

The deepest design principle of sci-adk is the separation of *record* from *belief*.

**The record is monotone.** An Evidence log only ever grows. An `EvidenceItem` is never mutated or deleted after it is appended (invariant E1). Null results, refuting results, and inconclusive results are valid, complete outcomes of the same type as positive ones (E2). This is not a convenience feature; it is the property that makes the log useful for verification. A log that can be silently amended or trimmed cannot be trusted as the basis for a reproducibility check.

**Belief is non-monotone.** A `Claim` is a revisable confidence state derived from the Evidence log by evaluating the frozen decision rule declared in the `Spec`. A claim whose status is `supported` can become `contested` or `refuted` when new Evidence arrives (invariant C1). Every status change appends a `StatusChange` record to the Claim's history, citing the triggering Evidence (C2), so the belief is non-monotone but its *history* is append-only. The important point is that this movement is not a bug or a failure state; it is the expected response to a growing record.

The `Spec` is the third type and functions as the frozen pre-registration contract. It carries the hypotheses, their decision rules, and their target claims. A frozen Spec version is immutable (S1); changes create a new version (S2) and require a human checkpoint even in autonomous execution mode (S5). The decision rule per hypothesis (S2) specifies how continuous or uncertain evidence maps to a belief state (S3): it can be a threshold rule (a scalar statistic compared to a cutoff), a categorical rule, or an interval rule. The crucial point is that there are no global hard-coded success thresholds in the system. Each Spec declares its own rule, per hypothesis, and the Claim's status is judged against *that* rule and no other. There is nothing to game because there is no universal passing bar.

The object graph these types induce is:

```
Spec  ──(frozen hypotheses + decision rules)──┐
                                              │
Evidence (append-only) ──────────────────────►│  Claim (revisable status)
                                              │
           Each EvidenceItem bears_on ────────┘
```

`Claim.evidence_set` includes both supporting and refuting links (C5). A claim derived from exploratory evidence is marked `exploratory` and cannot be promoted to `strict` without additional evidence under a stricter rule (C6). Confidence carries a natural-language `basis` field that is the load-bearing human-readable justification; a numerical value without an explanatory basis is explicitly insufficient (C3).

The separation between record and belief is what enables offline re-verification. The Evidence log is a file on disk. The Spec is a file on disk. The verdict is the output of a pure function over those two files. An LLM is not in the loop because LLM outputs are not deterministic and cannot be reproduced by a third party without access to the same model, version, and temperature settings.

---

## 3. The Verification Gate

`sci-adk verify` is the central command. It re-applies each Spec's frozen `DecisionRule` to the recorded Evidence and reports, per recorded Claim, one of three outcomes:

- **REPRODUCED**: the frozen rule, applied to the current Evidence log, yields the same belief status as the recorded Claim.
- **DIVERGED**: the rule yields a different status — indicating that the record has changed (new evidence arrived) or that the Claim was not correctly derived.
- **UNRESOLVED**: evidence is present but insufficient to trigger the rule in either direction.

The command exits non-zero unless every recorded Claim produces REPRODUCED. This makes `verify` scriptable: it can be placed in a continuous-integration pipeline, a pre-publication checklist, or a reviewer's shell script.

For numeric decision rules (threshold, interval), the engine is purely algorithmic: it reads the evidence item's result scalar, applies the comparison, and produces a boolean verdict. No language model is involved.

For non-numeric or judgment-based decision rules, the engine uses a `RecordedJudge`: it re-reads the recorded reasoning trails from the Evidence log rather than invoking a language model. The judge is deterministic in the sense that it reads from the fixed, append-only record, not from a live model call. The recorded trails were produced by an agent during the run; the verify audit re-reads those trails and re-derives the verdict from the text without re-invoking the agent. The seam between the in-session capability (which used an LLM) and the offline verify (which does not) is exactly here.

The reporting granularity is per-Claim, not per-run. A run with ten claims can have nine REPRODUCED and one DIVERGED; the specific DIVERGED claim is identified, and the tool exits non-zero because the record-as-a-whole does not reproduce. The researcher must resolve the divergence — by appending new evidence and re-deriving the claim, or by issuing a spec amendment — before the run is considered verified.

This design explicitly does not verify scientific validity. It verifies that the recorded evidence satisfies the pre-registered rules, and only that. Whether the experiment was correctly designed, whether the data was correctly collected, whether the rule is scientifically appropriate for the domain — these questions are outside the gate's scope. The gate is a necessary condition for a trustworthy record, not a sufficient condition for a true result.

---

## 4. Verdict Independence: What the Mechanisms Buy

The verify gate's usefulness depends on the verdict being independent of the agent that produced the work. Two mechanisms support this, and the tool is precise about what each one guarantees.

**Spec-freeze ordering.** The `Spec`, including every `DecisionRule`, is authored and frozen as the first stage of a run, before any Evidence is appended. This intra-run ordering means the decision rule cannot be rewritten to fit the evidence after the fact, within a single run. This is analogous to pre-registration in empirical science [@prereg]: it establishes a committed-before-looking discipline.

What this does *not* guarantee: the freeze ordering does not stop an operator from discarding an unsatisfying run and starting a new one with a different Spec, retroactively fitted to a result they already saw. This is cross-run rule-shopping, and it is a genuine residual risk. Addressing it fully would require committing the Spec to an external, third-party-timestamped store (a pre-registration registry, a public git repository with a trusted timestamp) before execution begins. sci-adk does not currently implement this. The discipline at present is good-faith commitment by the researcher.

**Record digest.** The Evidence log carries a SHA-256 digest over the canonical `spec.json` plus the sorted evidence and verdict logs. `sci-adk verify` re-computes and checks this digest. If the record was altered after the run — an evidence item edited, a result changed — the digest check fails before the verdict logic runs.

What this does *not* guarantee: the digest is a tamper-evidence mechanism, not a tamper-prevention mechanism. It detects post-hoc alteration of an existing record. It does not prevent a new run being fabricated from scratch, nor does it timestamp the original record in a trustworthy way. The digest is useful for confirming "this is the record that was verified," not for establishing "this record was produced before the operator saw the result."

Together, the two mechanisms make a run's verdict auditable: a reviewer can confirm that the Spec was not amended after evidence was appended (because the Spec is frozen and the digest covers it), and can confirm that the evidence log was not altered after the verdict was computed (because the digest covers the logs). The residual gaps — cross-run rule-shopping and post-hoc run fabrication — require external pre-registration to close fully, and the tool is explicit about this.

---

## 5. The Kernel/Adapter Seam

sci-adk separates domain-free rigor from domain-specific capability through a structural seam between a *rigor kernel* and a *capability adapter*.

**The kernel** comprises `sci_adk.core` (the Spec, Evidence, and Claim types and their invariants), `sci_adk.loop` (the DecisionEngine and the verify audit), and `sci_adk.render` (the deterministic record-to-LaTeX renderer). The kernel carries no domain knowledge. It does not know what domain a Spec concerns, what language a computation runs in, or what a "molecule" is. Its three interfaces are: Verifier (evaluate a DecisionRule against Evidence results), Experiment (a callable that, when invoked, produces Evidence), and Judge (re-reads recorded reasoning trails to propose a verdict for non-numeric rules).

**The adapter** provides the concrete implementations of the Experiment and Judge interfaces for a particular domain. The adapter knows that the T-1 domain encodes molecular graphs as integers, that the computation runs in a Docker container with Python, and that the result to record is a collision count. The kernel does not know any of this. It receives an `ExperimentFn` callable and invokes it; whatever the callable does is the adapter's concern.

The one-way dependency is `adapter → kernel`. The kernel is never permitted to import from the adapter. This rule is enforced on every test run by an abstract-syntax-tree import lint: a kernel module that contains an import from the adapter package fails the test suite. The lint checks imports, not logic. It is a necessary, machine-checked boundary; it does not prove that no domain assumption can enter the kernel by any other route (a kernel function that interprets a domain-specific string passed through a generic field, for example). But it does ensure that the structural coupling — the one that survives refactoring and remains visible in code review — is absent.

The practical consequence is that adding a new domain requires only implementing the Experiment and Judge interfaces in the adapter layer, with zero kernel changes. The adapter-seam architecture was designed with explicit attention to this property (architecture decision F3 in the design documents). That the architecture supports a second domain without kernel edits is the basis for the domain-generality claim about the *kernel*. It is not a claim that sci-adk provides a turnkey system for every domain; the adapter must be authored per domain. The kernel/adapter boundary is the specific thing that is domain-general.

The verification kernel has been run, unmodified and with zero kernel edits, on a second domain (environmental toxicology, a study of BAF/BCF prediction in aquatic ecotoxicology) as corroboration of the architectural claim. That second study is independent ongoing research (paper in preparation); it is cited here as supporting evidence for the boundary, not as a formal proof of domain generality.

---

## 6. Spec-Layer Science Guards and Evidence Validity

Beyond the verification gate, sci-adk includes two further mechanisms that check scientific hygiene before a run begins.

### 6.1 The Five Science Guards (G1–G5)

The science guards are pure, no-LLM checks applied at spec-compile time. They surface at a single chokepoint (the `audit_spec_science` / `ClaimUpdater._evaluate_hypothesis` path) and fire as either spec-lint warnings or verdict-gate halts, depending on the guard and the declared strictness level. They are never automatic halts in the sense that they block execution irreversibly; a researcher resolves them via the existing spec-amendment mechanism.

**G1 — Analyticity.** For a formal hypothesis with a threshold decision rule and a `finding`-type epistemic claim, G1 checks that the hypothesis carries a novelty declaration (either `novelty_result` or `novelty_method`). Without this, a purely computational result is indistinguishable from a definitional one — the experiment might be measuring a property that is analytically entailed by the method, not a genuine empirical finding about the domain. G1 fires both at spec-compile time and at the verdict gate.

**G2 — Test-power.** A decision rule is only as good as the test set it is applied to. G2 checks that a hypothesis carries at least one `discriminating_case` — a specific hard case (a near-miss, a degenerate instance, a boundary condition) that a correct method must handle. Without a discriminating case, the rule could be satisfied by a trivial implementation that only succeeds on easy inputs.

**G3 — Falsifiability.** The most important guard. For a formal hypothesis requiring strict support, G3 checks that the spec includes a negative control: an evidence item that applies a mutant or corrupted version of the method and confirms that the mutant fails on the discriminating cases. A method that has never been tested against a failure mode has not been tested at all. G3 is explicitly the guard that makes the test set non-trivial: the negative control must fail on the hard cases (G2's discriminating cases), not only on easy ones.

**G4 — Mode-coherence.** The `mode` field of a hypothesis (`exploratory` vs `confirmatory`) must be consistent with the decision rule's stringency. A frozen pre-registered pass/fail threshold belongs to a `confirmatory` hypothesis; an `exploratory` hypothesis's rule should be a guide, not a binding gate. An `exploratory` hypothesis carrying a binding threshold rule signals a mismatch between the researcher's stated uncertainty and the standard they are applying. Resolution: set `mode = confirmatory`, or use a non-threshold (guiding) rule for genuinely exploratory work.

**G5 — Claim-cost.** A spec-level lint that flags hypotheses containing language implying unconditional universality ("all", "any", "complete", "always") without corresponding cost metrics or scope declarations. A claim of universal scope without stated scope limitations is almost certainly overstated. G5 is a keyword lint, not natural-language understanding; it does not fire on a narrowly-worded spec that avoids universality language.

The honest limit of the guards is precise and documented: they enforce that the *declarations* each guard demands are present, not that those declarations are substantively correct. A discriminating case declared as hard may be easy; a negative control declared as failing may be incorrectly designed. The guards make the researcher's claimed rigor commitments legible and machine-checkable; they cannot independently verify that the commitments are fulfilled.

### 6.2 The Referent-Typed Evidence-Validity Gate

This gate addresses a failure mode observed in practice: a pipeline was given an empirical proposal (predicting rice organ dry-weight from measured plant traits), no real data was acquired, the system generated synthetic numbers directly, and the engine reported four hypotheses SUPPORTED with a "validated milestone" summary. The structural defect was that synthetic data was treated as valid evidence for an empirical claim. The gate fixes this by making evidence validity a referent-typed, load-bearing check rather than an advisory flag.

Every hypothesis carries a frozen `referent` field:
- `formal` — the claim is about a mathematical or algorithmic object; generated instances genuinely instantiate the referent.
- `empirical` — the claim is about a physical, biological, or clinical phenomenon; the referent lives outside the program and cannot be instantiated by synthetic data.

`referent` is frozen in the Spec at creation time. It cannot be relabelled from `empirical` to `formal` after execution to dodge the gate. The default is `empirical` — fail-closed. An unmarked hypothesis is treated as empirical, so an omitted label can never silently weaken the gate.

The gate has three rules. First: any `synthetic_proxy` evidence item bearing on an empirical hypothesis triggers a hard halt (category error — fabricated stand-in for an external referent). Second: an empirical hypothesis whose evidence yields a binding verdict (SUPPORTS or REFUTES) with no `measured` evidence item halts (no real data). An empirical hypothesis can accumulate `proposed` or `unresolved` status from non-measured evidence without halting, because no binding belief is asserted. Third: `generated` evidence on a `formal` hypothesis is allowed, because a generated instance genuinely instantiates a formal referent.

The T-1 run is the canonical illustration of the formal/generated case. T-1's hypothesis concerns injectivity of a Gödel-style encoding over a generated set of molecular graphs. The referent is the encoding algorithm's behavior, not an external physical phenomenon. The generated graph set is the actual population the claim quantifies over. A zero collision count over that set is a genuine computational result, not a synthetic proxy for anything external. The gate allows it, and the claim reaches SUPPORTED.

---

## 7. Related Work

**Workflow and provenance tools.** Snakemake [@snakemake] and comparable pipeline engines record how a result was produced: the directed acyclic graph of computations, the input/output files, the execution environment. DVC versions data and pipelines alongside code. Sumatra [@sumatra] and ReproZip [@reprozip] capture fine-grained execution provenance. These tools address reproducibility at the *record* level: given the same inputs and environment, reproduce the same outputs. sci-adk reuses and builds on this layer — a run directory is git-tracked — and adds the part these tools deliberately leave to the researcher: a typed, revisable belief state and a deterministic gate that decides whether a recorded claim is *currently* supported by the recorded evidence under the pre-registered rules.

**Truth-maintenance and provenance models.** Doyle's truth maintenance system [@doyle] and de Kleer's assumption-based TMS [@dekleer] established the formal distinction between a monotone belief base (the record of what was asserted) and a non-monotone derived belief state (what is currently believed, given the dependency structure). sci-adk's record/belief separation is a direct intellectual descendant of this work, adapted to the setting of empirical research rather than deductive knowledge bases. The W3C PROV data model [@prov] provides a standard vocabulary for provenance that sci-adk's Evidence type is aligned with: every evidence item carries Provenance including code references and environment identifiers. Pre-registration in empirical science [@prereg] provides the procedural analogue of the spec-freeze: commit to hypothesis and decision rule before execution. sci-adk implements this discipline computationally.

**Event sourcing.** The append-only Evidence log is structurally an event log in the sense of event-sourcing architectures: state (Claim status) is derived by replaying events (Evidence items through Decision rules) rather than being stored directly as mutable state. This makes the verification step a replay audit, which is why it is deterministic and offline-capable.

**Agent audit and evidence binding.** The AI Scientist [@aiscientist] demonstrated fully automated research generation but does not address the self-certification problem. Evidence-bound autonomous research [@evibound] proposes a governance framework requiring evidence citation for every claim. Claim-level auditability work [@aar] argues for auditable reasoning traces in deep research agents. sci-adk's distinguishing commitment relative to these approaches is architectural: the verdict path contains no language model at any point, and the verification function is a deterministic computation over typed JSON files. The auditability is not a property of the agent's reasoning; it is a property of the data structures and the pure function applied to them.

---

## 8. Worked Example: T-1

The bundled T-1 run (`runs/t1-godel/`) provides a concrete, end-to-end illustration of the architecture. T-1 is a number-theoretic molecular numbering scheme — a Gödel-style prime-product encoding of molecular graphs — that is an independently motivated problem from the author's mathematics-to-computational-chemistry program. It is not a demonstration built to drive the tool; the mathematical treatment of T-1 is independent ongoing work. The sci-adk run of T-1 illustrates the tool's architecture.

**The Spec.** The `runs/t1-godel/spec.json` file contains a single hypothesis, `hyp-t1`: "Molecule graphs admit an injective Gödel-style encoding on the tested set." The `mode` is `exploratory`. The `referent` is `formal`: the claim is about an algorithm's behavior over a generated set of molecular graphs, not about any physical phenomenon. The `decision_rule` is a threshold: `collision_count == 0` over the test set yields `support`; any positive collision count yields `refute`. The `non_circularity` field attests that the generator emits molecular graphs with no guarantee of distinct codes, so a zero collision count is informative: "a zero count is therefore informative, not a property baked into the generator." This satisfies the evidence-validity gate's non-circularity requirement for formal/generated evidence. The Spec was frozen at creation time, before execution.

**The Evidence.** The evidence item `evi-t1-20260616-111516-ddcad848.json` records the result of the T-1 experiment run. The `kind` is `experiment_run`. The `provenance` records the code commit SHA (`6800c510f53eb912fcc1a459059d9ac633db2d11`), the execution environment (`capability:t1-molecular-godel, docker:sci-adk-python-base, image_id:f4b2801533cb`), and the timestamp. The `result` records: `collision_count: 0`, `round_trip_ok: true`, `n_molecules: 6`. The `bears_on` field links the evidence to `hyp-t1` with `direction: supports`.

**The Claim.** The `claim-hyp-t1.json` file records: `status: supported`, `confidence.basis: "threshold rule: statistic 'point'=0 == 0 is met"`. The `history` shows one status transition: from `proposed` to `supported`, triggered by the evidence item, via the DecisionEngine.

**The Verify Audit.** Running `sci-adk verify` on this run: the engine reads `spec.json`, reads the evidence log, reads the claim file, re-applies the threshold rule (`collision_count == 0`), finds the recorded result (`point: 0.0`) satisfies the rule, and reports REPRODUCED. The command exits 0. The record-digest check confirms the evidence log has not been altered since the verdict was recorded.

The scope of the result is precisely what the Spec states: injectivity on a six-molecule test set, in an exploratory mode. The result does not claim universal injectivity or generality beyond the tested set. The claim-cost guard (G5) does not fire because the hypothesis statement is narrowly worded with no universality language. The analyticity guard (G1) fires in the current T-1 Spec because `discriminating_cases` and a novelty declaration were not included in this illustrative version; the guard behavior is consistent with the documented example in the science-guards design (§6, the `t1-godel(v4)` example).

---

## 9. Limitations and Honesty Boundaries

The following boundaries are stated explicitly. They are not caveats appended as a formality; they are load-bearing constraints on what the tool claims.

**Internal consistency, not validity.** `sci-adk verify` checks whether the recorded evidence satisfies the pre-registered rules. It does not check whether the experiment was correctly designed, whether the data was correctly collected, whether the decision rule is scientifically appropriate for the domain, or whether the result is true in any external sense. These questions are outside the gate's scope. A run can be fully verified (every claim REPRODUCED) and still be scientifically wrong if the experiment was designed to produce a foregone conclusion. The gate is a necessary condition for a trustworthy record under stated rules, not a sufficient condition for scientific truth.

**The spec-freeze does not stop run-discard-and-respecify.** The intra-run spec-freeze ensures that within a single run, the decision rule cannot be changed after evidence is appended. It does not stop an operator from running an experiment, observing the result, discarding the run, changing the Spec, and running again. Cross-run rule-shopping is a real residual risk. A hard temporal guarantee requires committing the Spec to an external timestamped store before execution. sci-adk's discipline is good-faith commitment, analogous to pre-registration rather than a cryptographic guarantee.

**The record digest detects tampering, does not prevent fabrication.** The SHA-256 digest over the spec and evidence logs detects post-hoc alteration of an existing record. It does not prevent a new record being fabricated from scratch with desired values, nor does it provide a trusted timestamp. The two mechanisms — freeze ordering and digest — together make a run's record auditable, but they do not replace the trust the research community places in the researcher's integrity.

**Domain generality applies to the verification kernel only.** The kernel/adapter boundary is machine-enforced; the kernel contains no domain content. The verification kernel has been run on a second domain (environmental toxicology) without kernel edits, providing corroboration for the architectural claim. This is not a claim that sci-adk provides a ready-made system for any arbitrary domain. Each new domain requires authoring a capability adapter. The kernel/adapter seam is the general part; the adapters are domain-specific work.

**The autonomous-experiment adapter seam is exercised on T-1 only.** The capability adapter for the T-1 molecular experiment is the only adapter that has been fully exercised end-to-end through the automated execution loop. The architecture is designed to support additional adapters (this was the explicit motivation for the adapter-registry mechanism, architecture decision F3), but a second fully-automated adapter is not implemented. This limitation is not claimed as cross-domain.

**The science guards enforce declaration presence, not substantive quality.** A discriminating case declared as hard may be easy; a negative control declared as failing may be incorrectly designed; a non-circularity attestation may be wrong. The guards make the researcher's rigor commitments machine-checkable; they cannot independently verify that those commitments are substantively fulfilled.

**AI usage.** The source code and this paper were developed with substantial AI assistance (agentic coding and drafting with large language models) under a human verification gate. Every change and claim was reviewed and accepted by the author, who is responsible for all content. The automated test suite is the acceptance check for the software.

---

## 10. Conclusion

We have described the design of sci-adk's verification architecture, with emphasis on the mechanisms that separate the research record from belief and make the verdict on a recorded claim deterministic, LLM-free, and reproducible offline.

The central contribution is architectural: by keeping the verdict path outside the agent — in a pure function over typed JSON files — the tool provides a structural guarantee that the agent producing the work cannot be the sole assessor of whether it succeeded. The record/belief separation makes null and negative results first-class, because the Evidence log is append-only and refuting evidence is a valid EvidenceItem. The spec-freeze ordering and record digest together make a run auditable: within a run, the decision rule predates the evidence; across runs, the digest detects post-hoc alteration. The kernel/adapter seam, enforced by an AST import lint, keeps the rigor machinery domain-free while permitting domain capability to be added by implementing three interfaces.

The tool is explicit about what each mechanism does not guarantee. The verify gate checks internal consistency, not scientific validity. The spec-freeze does not stop cross-run rule-shopping without an external timestamped pre-registration. The record digest detects tampering but does not prevent fabrication. Domain generality is a property of the kernel and its machine-enforced boundary, corroborated by a second-domain run, not a blanket claim about the whole system.

As AI systems take on more autonomous research roles, the separation between the agent that proposes and the mechanism that judges becomes a design requirement rather than a design option. The architecture described here is one approach to that requirement: deterministic, offline-capable, and honest about its limits.

---

## Acknowledgements

The author carried out this work as independent research with no specific grant funding. [Author to confirm this statement is literally accurate before posting.]

---

## AI Usage Disclosure

The source code of sci-adk and this paper were developed with substantial AI assistance (agentic coding and drafting with large language models) under a human verification gate. Every change and every claim was reviewed and accepted by the author, who is solely responsible for all content. The automated test suite (`pytest`, continuous integration on Python 3.11 and 3.12) is the acceptance check for the software.

---

## References

[@doyle]: Doyle, J. (1979). A truth maintenance system. *Artificial Intelligence*, 12(3), 231–272. doi:10.1016/0004-3702(79)90008-0

[@dekleer]: de Kleer, J. (1986). An assumption-based TMS. *Artificial Intelligence*, 28(2), 127–162. doi:10.1016/0004-3702(86)90080-9

[@prov]: Moreau, L. & Missier, P. (2013). PROV-DM: The PROV Data Model. W3C Recommendation.

[@prereg]: Nosek, B. A. et al. (2018). The preregistration revolution. *PNAS*, 115(11), 2600–2606. doi:10.1073/pnas.1708274114

[@snakemake]: Köster, J. & Rahmann, S. (2012). Snakemake — a scalable bioinformatics workflow engine. *Bioinformatics*, 28(19), 2520–2522. doi:10.1093/bioinformatics/bts480

[@sumatra]: Davison, A. P. (2012). Automated capture of experiment context for easier reproducibility in computational research. *Computing in Science & Engineering*, 14(4), 48–56. doi:10.1109/MCSE.2012.41

[@reprozip]: Chirigati, F. et al. (2016). ReproZip: Computational Reproducibility With Ease. *SIGMOD '16*, 2085–2088. doi:10.1145/2882903.2899401

[@evibound]: Chen, R. (2025). Evidence-Bound Autonomous Research (EviBound): A Governance Framework for Eliminating False Claims. arXiv:2511.05524. doi:10.48550/arXiv.2511.05524

[@aar]: Rasheed, R. A. et al. (2026). From Fluent to Verifiable: Claim-Level Auditability for Deep Research Agents. arXiv:2602.13855. doi:10.48550/arXiv.2602.13855

[@aiscientist]: Lu, C. et al. (2024). The AI Scientist: Towards Fully Automated Open-Ended Scientific Discovery. arXiv:2408.06292. doi:10.48550/arXiv.2408.06292
