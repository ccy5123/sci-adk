"""
``sci-adk verify`` -- the headless, read-only belief audit (F6).

design/rigor-shell-architecture.md §6.2 / §7.1 / §8 F6: a third party re-derives the
belief from the *recorded* run and confirms it follows from the record -- WITHOUT
Claude Code. ``verify_run`` is the kernel-side function behind the CLI verb.

What it does, per hypothesis that has a recorded ``Claim``:

  1. Re-apply the FROZEN ``DecisionRule`` to the RECORDED Evidence via
     ``DecisionEngine.evaluate(rule, results)`` -- the SAME pure call ``ClaimUpdater``
     makes, but here with NO persistence and NO claim mutation:
       - numeric kinds (threshold/bayesian/interval) re-evaluate autonomously;
       - non-numeric kinds (proof/qualitative) get a ``RecordedJudge(run_dir)``
         injected, so the engine re-reads the recorded ``verdicts/*.json`` trail and
         re-applies the frozen rule + the F2 gate -- deterministic, NO LLM. A
         non-numeric hypothesis whose trail is absent -> the engine returns
         ``inconclusive`` (F2) -> reported UNRESOLVED ("not reproducible from record").
  2. Map the re-derived ``Verdict`` to a ``ClaimStatus`` through the SINGLE public
     source of truth ``claim_updater.status_for_verdict`` (the direction->status
     mapping + the CONTESTED override on the raw bearings) that ``ClaimUpdater`` also
     uses to persist -- so a faithful record reproduces exactly, with no duplicated
     derivation to drift.
  3. Compare the re-derived status to the recorded ``Claim.status``:
       - same binding status            -> REPRODUCED
       - re-derived inconclusive        -> UNRESOLVED (record does not re-derive)
       - any other mismatch             -> DIVERGED

The run is reproduced iff every recorded claim is REPRODUCED -- the verb's exit code.

Read-only invariants (any violation = failure):
  - re-runs NO experiment (no ``ExperimentFn`` is invoked),
  - calls NO LLM / capability (the only judge is the deterministic ``RecordedJudge``),
  - overwrites NO recorded file (re-derivation is entirely in memory).

The report also carries the :func:`sci_adk.provenance.record_digest` of the run, the
tamper-evidence companion a third party compares against a trusted baseline.

This module is KERNEL-side: it reads only the single append-only Evidence log + spec
+ verdict trails, and uses only deterministic deserialization (``RecordedJudge`` is
kernel-side pure JSON; no ``kernel -> adapter`` import).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Literal, Optional

from sci_adk.core.claim import Claim, ClaimStatus
from sci_adk.core.evidence import BearingDirection, EvidenceItem, EvidenceKind
from sci_adk.core.pkgreqs import (
    DEFAULT_REQUIRED_SECTIONS as PKG_DEFAULT_REQUIRED_SECTIONS,
)
from sci_adk.core.pkgreqs import PackageReqs
from sci_adk.core.pubreqs import (
    DEFAULT_REQUIRED_SECTIONS as PUB_DEFAULT_REQUIRED_SECTIONS,
)
from sci_adk.core.pubreqs import PubReqs
from sci_adk.core.spec import Hypothesis, Spec
from sci_adk.core.validity import (
    ValidityHalt,
    check_analyticity,
    check_digitized_adequacy,
    check_discriminating_power,
    check_falsifiability_adequacy,
    derive_novelty_status,
)
from sci_adk.loop.claim_updater import counted_evidence, status_for_verdict
from sci_adk.loop.compiler import deposit_record_path
from sci_adk.loop.decision_engine import DecisionEngine, EvidenceForHypothesis
from sci_adk.loop.prior_work import prior_work_open
from sci_adk.loop.recorded_judge import RecordedJudge
from sci_adk.provenance import record_digest
from sci_adk.render.consistency import (
    LatexRefReport,
    check_cross_doc_s_refs,
    check_latex_ref_consistency,
)
from sci_adk.render.factref import find_unresolved_factrefs
from sci_adk.render.novelty import find_unsupported_novelty
from sci_adk.render.number_audit import (
    RecordedValuePool,
    number_audit_problems,
    pool_from_record,
)
from sci_adk.render.paper import check_paper_tool_vocabulary
from sci_adk.render.pkgreqs_checks import (
    abstract_max_words_problems,
    bib_latex_safety_problems,
    body_word_range_problems,
    citation_disambiguation_problems,
    citation_key_shape_problems,
    cite_resolution_problems,
    deposit_completeness_problems,
    figure_presence_problems,
    layout_problems,
    package_record_path,
    readme_submission_readiness_problems,
    unpublished_citation_warnings,
)
from sci_adk.render.pubreqs_checks import (
    figure_font_policy_problems,
    image_dpi_problems,
    max_words_problems,
    reference_style_problems,
    required_sections_problems,
    section_order_problems,
)

# The rendered paper SUBMISSION documents verify re-checks for internal \ref<->\label
# integrity (design/paper-figures-and-si.md D4, Phase 3). Both are checked WITHIN
# themselves; the cross-DOCUMENT main<->SI reference (the plain-text "Figure S<n>" /
# "Table S<n>" a real \ref cannot carry across the compile boundary) is gated SEPARATELY
# and statically by _check_cross_doc_refs (it counts SI floats, no xr package, no
# recompile). A document absent from paper/ is simply skipped.
#
# SPEC-SI-AUTHORING-001: si.tex is now an AUTHORED belief artifact (the overflow of the
# main paper), NOT the record dump -- so BOTH draft.tex and si.tex are submission
# documents audited as manuscripts (P2 number-audit, value-fidelity, novelty, cross-doc,
# and now the per-run tool-vocab gate, REQ-SA-204). The deterministic record dump was
# RELOCATED to the deposit's record.tex (which lives OUTSIDE paper/ and is NOT in this
# tuple, so it is never scanned by these paper gates; REQ-SA-206).
_PAPER_DOCS: tuple[str, ...] = ("draft.tex", "si.tex")

# The merged-manuscript documents the workspace-PACKAGE gate checks (design/near-submission-
# package.md §3). BOTH main.tex and si.tex are tool-agnostic SUBMISSION documents (the merged
# manuscript reads as science end to end); the package tool-vocab scan covers both. (Under
# SPEC-SI-AUTHORING-001 the per-run gate matches this -- si.tex is no longer the record dump.)
# The deterministic record lives in the deposit (record.tex), not in package/01_manuscript/.
_PACKAGE_MAIN: str = "main.tex"
_PACKAGE_SI: str = "si.tex"
_PACKAGE_DOCS: tuple[str, ...] = (_PACKAGE_MAIN, _PACKAGE_SI)
# The authored package si.tex's OWN bibliography (SPEC-SI-AUTHORING-001 M6): a cited-only
# subset of the package pool the SI cite-resolution gate resolves si.tex's \cite* against.
_REFERENCES_SI_BIB: str = "references_SI.bib"

# Per-hypothesis audit results. Strings (not an enum) keep the report trivially
# printable/serializable; the set is closed and small.
REPRODUCED = "REPRODUCED"
DIVERGED = "DIVERGED"
UNRESOLVED = "UNRESOLVED"


@dataclass(frozen=True)
class VerifyOutcome:
    """The audit result for one recorded Claim (one hypothesis).

    Attributes:
        hypothesis_id: the hypothesis the recorded Claim answers.
        recorded_status: the ``Claim.status`` read from ``claims/*.json``.
        rederived_status: the status re-derived from the frozen rule + recorded
            Evidence/trail (``None`` only if the engine could not produce one, which
            it always can -- inconclusive is a status-bearing verdict).
        result: ``REPRODUCED`` | ``DIVERGED`` | ``UNRESOLVED``.
        rederived_basis: the re-derived ``Verdict.confidence.basis`` (the audit's
            own justification, distinct from the recorded claim's basis).
    """

    hypothesis_id: str
    recorded_status: ClaimStatus
    rederived_status: Optional[ClaimStatus]
    result: str
    rederived_basis: str


@dataclass(frozen=True)
class VerifyReport:
    """The outcome of a headless verify over a run dir.

    Attributes:
        spec_id: the recorded Spec id.
        outcomes: one :class:`VerifyOutcome` per recorded Claim.
        digest: the record digest (tamper-evidence companion, §8 F6).
        all_reproduced: True iff every recorded claim REPRODUCED -- the CLAIMS-only
            signal. Its meaning is UNCHANGED by Phase 3 (existing callers read it as the
            belief-reproduction signal); the paper gate lives in the fields below.
        paper_consistency: per-paper-document (``draft.tex`` / ``si.tex``) internal
            ``\\ref``<->``\\label`` reports (D4, Phase 3), keyed by file name. EMPTY when
            the run has no ``paper/`` directory (or neither document is present).
        paper_consistent: True iff EVERY present paper document's report is ``ok`` --
            and True (vacuously) when there is no paper to check. The paper HARD gate.
        paper_factrefs: per-paper-document residual ``\\evval``/``\\status`` macros (the
            record-fidelity fact markup), keyed by file name. A rendered ``.tex`` should
            contain NONE -- the engine substitutes them all at render time -- so a residual
            means substitution was bypassed or the ``.tex`` was hand-edited (a fidelity
            divergence). EMPTY when clean / no paper.
        paper_factref_clean: True iff no paper document carries a residual factref macro
            (and True vacuously with no paper). Part of the HARD gate.
        paper_tool_vocab: tool-vocabulary leaks (§10) found in the SUBMISSION documents
            (``draft.tex`` AND the authored ``si.tex`` -- SPEC-SI-AUTHORING-001 REQ-SA-204
            lifted the old SI exemption; the deposit's ``record.tex`` stays EXEMPT,
            REQ-SA-206): phrases/words that name the sci-adk machinery instead of the
            science (``sci-adk``, ``frozen Spec``, ``verdict``, ``Evidence record``, ...).
            EMPTY when the submission documents read as tool-agnostic science / no paper.
        paper_tool_clean: True iff no submission document carries a tool-vocabulary leak
            (and True vacuously with no draft.tex/si.tex). Part of the HARD gate.
        paper_novelty_problems: per-paper-document ``\\novelty{kind}{hyp}{...}`` assertions
            (the novelty/priority markup) that do NOT re-derive SUPPORTED from the record
            (N3 gate), keyed by file name. A SUPPORTED assertion is silent; an unsupported /
            unknown-hyp / bad-kind one (e.g. the backing ``found_nothing`` decision was
            deleted) is a problem line. EMPTY when clean / no paper. BOTH ``draft.tex`` and
            ``si.tex`` are scanned (no gap where an author sneaks ``\\novelty`` into SI prose).
        paper_novelty_clean: True iff no paper document carries an unsupported novelty
            assertion (and True vacuously with no paper). Part of the HARD gate.
        paper_cross_doc_refs: every plain-text "Figure S<n>" / "Table S<n>" the MAIN paper
            (``draft.tex``) cites that points past the SI's float count -- a silent dangling
            cross-document reference (the SI renumbers its floats ``S1, S2, ...`` and a real
            ``\\ref`` cannot cross the compile boundary, so these are bare text the within-
            document gate never sees). EMPTY when clean, or when either ``draft.tex`` or
            ``si.tex`` is absent (the gate needs both documents).
        paper_cross_doc_clean: True iff the main paper cites no dangling SI float (and True
            vacuously when both documents are not present). Part of the HARD gate.
        paper_requirements_problems: the F1 publishing-requirements failures (design §1.3) the
            frozen ``pubreqs.json`` declared and the rendered paper does NOT meet -- missing
            required sections, a stripped F2 font preamble, a below-threshold raster DPI, an
            unwired reference style, an over-limit word count, or a missing reproduction
            bundle. EMPTY when the contract is met OR when there is NO ``pubreqs.json`` (a run
            with no declared requirements is vacuously clean -- backward compatible). ADVISORY
            items and ``max_pages`` are NEVER in this list (they are surfaced, never gated).
        paper_requirements_clean: True iff no declared publishing requirement failed (and True
            vacuously when ``pubreqs.json`` is absent). Part of the HARD gate.
        paper_advisory: per-run NON-BLOCKING advisory lines (SPEC-PAPER-GATE-001 OD-5/OD-6) --
            an unpublished/DOI-less load-bearing citation, or a section order that deviates from
            the default IMRaD order when NO order was declared. SURFACED in the CLI, NEVER gated
            (not in ``passed``). The per-run companion to ``PackageVerifyReport.advisory``. EMPTY
            when clean / no paper / no contract. Closing the per-run advisory-channel gap the
            package gate already had.
        deposit_problems: the RECORD-side deposit-completeness problems (SPEC-SI-AUTHORING-001
            M2, Pillar C) -- presence-only lines naming a deposit element that is absent: the
            retained deterministic record artifact (located via ``deposit_record_path``, the M1
            single source of truth) and/or a "Data & code availability" statement in it. PURE,
            deterministic, no LLM (REQ-SA-304); it judges ONLY presence, never belief content.
            ADDITIVE (REQ-SA-305): surfaced as its OWN channel -- it never weakens or replaces
            the existing claim-reproduction / record-green audit (``all_reproduced``). EMPTY
            when the deposit carries both elements.
        deposit_complete: True iff the deposit carries both record-side elements (i.e.
            ``deposit_problems`` is empty). The record-side companion to the belief-side
            ``paper_*_clean`` flags.
        passed: the COMBINED exit gate -- ``all_reproduced and paper_consistent and
            paper_factref_clean and paper_tool_clean and paper_novelty_clean and
            paper_cross_doc_clean and paper_requirements_clean``. This is what the CLI exits
            on; ``all_reproduced`` alone is the claim signal.
    """

    spec_id: str
    outcomes: List[VerifyOutcome]
    digest: str
    all_reproduced: bool = field(default=False)
    paper_consistency: Dict[str, LatexRefReport] = field(default_factory=dict)
    paper_consistent: bool = field(default=True)
    paper_factrefs: Dict[str, List[str]] = field(default_factory=dict)
    paper_factref_clean: bool = field(default=True)
    paper_tool_vocab: List[str] = field(default_factory=list)
    paper_tool_clean: bool = field(default=True)
    paper_novelty_problems: Dict[str, List[str]] = field(default_factory=dict)
    paper_novelty_clean: bool = field(default=True)
    paper_cross_doc_refs: List[str] = field(default_factory=list)
    paper_cross_doc_clean: bool = field(default=True)
    paper_requirements_problems: List[str] = field(default_factory=list)
    paper_requirements_clean: bool = field(default=True)
    paper_advisory: List[str] = field(default_factory=list)
    deposit_problems: List[str] = field(default_factory=list)
    deposit_complete: bool = field(default=True)
    passed: bool = field(default=False)


@dataclass(frozen=True)
class PackageVerifyReport:
    """The outcome of the workspace-level PACKAGE gate (design/near-submission-package.md §3).

    The umbrella ``package_requirements_clean`` gate over an assembled ``<ws>/package/`` and
    its FROZEN ``<ws>/pkgreqs.json``: a deterministic, read-only, no-LLM audit of the merged
    submission. It is the workspace-scope companion to :class:`VerifyReport` (which is per-run);
    a package is not a run, so it carries its own report rather than overloading the per-run one.

    Attributes:
        workspace_dir: the workspace root audited.
        runs: the run ids the ``06_provenance/run_index.csv`` lists (the runs the package
            synthesizes). EMPTY when no package / no run index.
        runs_reproduced: per-run REPRODUCED-flag (True iff that run's record re-derives via the
            headless audit). A listed run that does NOT reproduce is a gate failure.
        package_requirements_problems: every declared package requirement the assembled package
            does NOT meet (design §3): a missing layout element, a broken main.tex/si.tex
            (ref/label, figure, brace, cite), a tool-vocabulary leak in main.tex, a missing
            required section, an over-limit abstract, an unwired reference style, a missing
            ``claims_all.csv`` / ``run_index.csv``, a non-reproducing run, a residual
            ``\\evval``/``\\status`` fidelity macro, or a README with no submission-readiness
            section. EMPTY when the package meets the contract OR when there is NO ``package/``
            (nothing to gate -- vacuously clean). When ``pkgreqs.json`` is ABSENT the
            venue-FORMAT sub-checks (required_sections / reference_style / abstract limit) are
            vacuously clean, but the layout/traceability/compile checks still run if a
            ``package/`` exists (design §3, backward compatible).
        advisory: the contract's body_word_range + free-form advisory, SURFACED never gated.
        package_requirements_clean: True iff no declared package requirement failed (and True
            vacuously when no ``package/`` exists). The HARD gate.
        passed: the package exit gate -- equal to ``package_requirements_clean`` (the package
            gate has no separate per-claim signal; the per-run reproduction is folded into the
            requirements as the ``record green`` check).
    """

    workspace_dir: Path
    runs: List[str] = field(default_factory=list)
    runs_reproduced: Dict[str, bool] = field(default_factory=dict)
    package_requirements_problems: List[str] = field(default_factory=list)
    advisory: List[str] = field(default_factory=list)
    package_requirements_clean: bool = field(default=True)
    passed: bool = field(default=True)


def verify_run(run_dir: Path, strict_science: bool = False) -> VerifyReport:
    """Re-derive belief from the recorded run and compare it to the recorded Claims.

    PURE + READ-ONLY: re-applies the frozen ``DecisionRule`` to the recorded Evidence
    (numeric autonomously; non-numeric via ``RecordedJudge`` re-reading the recorded
    trails + the F2 gate), entirely in memory. No experiment is re-run, no LLM is
    called, and no recorded file is modified.

    Args:
        run_dir: an existing ``runs/<spec.id>/`` directory.
        strict_science: when True, ALSO re-apply the science-guard verdict gates
            (design/science-guards.md G1/G2/G3) read-only over the recorded Evidence -- the
            tamper-evidence companion to the digitized re-check. A recorded SUPPORTED
            formal+threshold claim whose falsifying NEGATIVE_CONTROL was deleted (or whose
            discriminating cases were dropped) NO LONGER re-derives in strict mode -> the
            audit reports DIVERGED. Default False (the lenient PRIMITIVE contract): the
            science re-check is skipped, so a faithful record re-derives exactly as before
            (existing callers/behaviour unchanged). The CLI ``verify --strict-science`` opts in.

    Returns:
        A :class:`VerifyReport` -- inspect ``all_reproduced`` for the CI gate.

    Raises:
        FileNotFoundError: if ``spec.json`` is absent.
        ValueError: if a recorded artifact is malformed (RecordedJudge / loaders
            re-raise as a clear, file-naming ValueError).
    """
    # @MX:ANCHOR: [AUTO] the single headless re-derivation entry (F6) -- a third party
    #   re-derives belief from the record (numeric AND non-numeric) without Claude Code.
    # @MX:REASON: [AUTO] the CLI `verify` verb and the verify test suites call this; it
    #   owns the READ-ONLY + no-LLM + no-re-run audit contract and reuses the engine's
    #   pure evaluate() + ClaimUpdater's status mapping so a faithful record reproduces
    #   exactly. Persisting anything here, or diverging from the updater's mapping,
    #   would either mutate the audited record or produce false DIVERGED/REPRODUCED.
    run_dir = Path(run_dir)

    spec = _load_spec(run_dir)
    evidence = _load_evidence(run_dir)
    recorded_claims = _load_claims(run_dir)

    # The engine is pure and stateless; injecting RecordedJudge lets the non-numeric
    # kinds re-derive from the recorded trails (deterministic, no LLM). The numeric
    # kinds never touch the judge.
    engine = DecisionEngine(judge=RecordedJudge(run_dir))

    hyp_by_id: Dict[str, Hypothesis] = {h.id: h for h in spec.hypotheses}

    # Novelty decisions (bears_on=[]) never enter the engine, but the novelty claim
    # re-derivation needs them: a SUPPORTED novelty claim re-derives only if the record
    # still holds a *found_nothing* prior-art decision (B-replace). Gather once.
    novelty_decisions = [
        ev for ev in evidence if ev.kind == EvidenceKind.NOVELTY_DECISION
    ]

    # Negative controls (science-guards G3): the bears_on=[] apparatus-falsification records.
    # Gathered once for the strict-science re-check (tamper-evidence: a deleted control makes
    # a recorded strict SUPPORTED no longer re-derive).
    negative_controls = [
        ev for ev in evidence if ev.kind == EvidenceKind.NEGATIVE_CONTROL
    ]

    outcomes: List[VerifyOutcome] = []
    for claim_id, claim in sorted(recorded_claims.items()):
        hyp_id = claim.answers
        hypothesis = hyp_by_id.get(hyp_id)
        if hypothesis is None:
            # A recorded claim whose hypothesis is absent from the (frozen) Spec: the
            # record is internally inconsistent -- the belief cannot be re-derived from
            # this Spec version, so it does not reproduce.
            outcomes.append(
                VerifyOutcome(
                    hypothesis_id=hyp_id,
                    recorded_status=claim.status,
                    rederived_status=None,
                    result=DIVERGED,
                    rederived_basis=(
                        "recorded claim references a hypothesis absent from spec.json "
                        "(cannot re-derive belief from this Spec version)"
                    ),
                )
            )
            continue
        if _is_novelty_claim(claim):
            # Novelty claim (B-replace, 2-kind): re-derive its status by RULE
            # (``derive_novelty_status`` over the recorded novelty decisions for the
            # claim's KIND), NOT via the experiment DecisionEngine. The kind is parsed from
            # the claim id (``claim-novelty-{result,method}-<hyp>``). A deleted/tampered
            # found_nothing decision for that kind makes the recorded SUPPORTED novelty
            # claim no longer re-derive -> DIVERGED.
            kind = _novelty_kind_of(claim)
            outcomes.append(
                _audit_novelty_claim(hypothesis, kind, claim, novelty_decisions)
            )
            continue
        outcomes.append(
            _audit_hypothesis(
                engine, hypothesis, evidence, claim,
                strict_science=strict_science,
                negative_controls=negative_controls,
            )
        )

    all_reproduced = bool(outcomes) and all(o.result == REPRODUCED for o in outcomes)

    # Phase 3 (D4): re-check the RENDERED paper's internal \ref<->\label integrity, as a
    # third party would -- READ-ONLY (read each .tex; never recompile, never write, no
    # LLM). draft.tex AND si.tex, each WITHIN itself. A document not on disk is skipped;
    # a run with no paper/ -> empty map -> paper_consistent True (gate unchanged).
    paper_consistency = _check_paper_consistency(run_dir)
    paper_consistent = all(rep.ok for rep in paper_consistency.values())

    # Fidelity gate (the "moved line"): a rendered paper's record-derived facts are
    # written as \evval/\status macros that the engine substitutes at render time, so a
    # residual macro in the .tex means substitution was bypassed / the .tex was edited.
    # READ-ONLY, no recompile, no LLM -- the same third-party spirit as the ref/label check.
    paper_factrefs = _check_paper_factrefs(run_dir)
    paper_factref_clean = not any(paper_factrefs.values())

    # Tool-vocabulary gate (§10): the SUBMISSION documents (draft.tex AND the authored
    # si.tex; SPEC-SI-AUTHORING-001 REQ-SA-204) must read as tool-agnostic science. The
    # deposit's record.tex is EXEMPT (REQ-SA-206, lives outside paper/). READ-ONLY, no LLM.
    paper_tool_vocab = _check_paper_tool_vocab(run_dir)
    paper_tool_clean = not paper_tool_vocab

    # Novelty gate (N3): every \novelty{kind}{hyp}{...} in the paper (draft.tex AND si.tex)
    # must re-derive SUPPORTED from the recorded NOVELTY_DECISIONs -- else the paper asserts
    # a priority the record does not back. READ-ONLY, no recompile, no LLM.
    paper_novelty_problems = _check_paper_novelty(run_dir, spec, novelty_decisions)
    paper_novelty_clean = not any(paper_novelty_problems.values())

    # Cross-document gate: the main paper cites SI floats as plain text ("Figure S1") that a
    # real \ref cannot carry across the compile boundary, so a "Figure S3" with only two SI
    # figures is a silent dangling reference the within-document check never sees. Static
    # count of the SI's floats -- READ-ONLY, no recompile, no xr package, no LLM.
    paper_cross_doc_refs = _check_cross_doc_refs(run_dir)
    paper_cross_doc_clean = not paper_cross_doc_refs

    # Publishing-requirements gate (F1, design/paper-publishing-requirements.md §1.3): the
    # umbrella gate that consumes F2 (font/DPI) + F3 (reproduction bundle) + the section/
    # reference/word-count checks the FROZEN pubreqs.json declares. READ-ONLY, no recompile,
    # no LLM. SPEC-PAPER-GATE-001 P1+P2: when paper/draft.tex EXISTS (a conclusion-bearing
    # artifact, OD-1 strict) the gate is NO LONGER vacuous -- an absent pubreqs.json is a loud
    # REFUSAL (OD-8 immediate), and every quantitative token in draft.tex+si.tex must trace to
    # the recorded-value pool (P2 number-audit). A run with NO draft.tex stays vacuously clean.
    # advisory + max_pages are surfaced (CLI) but NEVER gated.
    paper_requirements_problems, paper_advisory = _check_paper_requirements(
        run_dir, evidence, list(recorded_claims.values()), spec
    )

    # Prior-work decision gate: a conclusion-bearing run (draft.tex present) must carry a
    # recorded prior-work DECISION -- searched or skipped-with-reason. This enforces the
    # design's own principle ("the discovery decision must be in the record",
    # design/literature-acquisition.md) at the publication surface; it does NOT force a
    # search (a recorded skip clears it). Reuses the conclusion-bearing scoping (draft.tex
    # present) so pre-paper exploratory runs stay unaffected.
    if (run_dir / "paper" / "draft.tex").is_file() and prior_work_open(
        spec, run_dir.parent.parent
    ):
        paper_requirements_problems = [
            *paper_requirements_problems,
            "prior-work decision not recorded: run `sci-adk prior-work <run-dir> "
            '--searched <dois...>` or `--skip --reason "..."` before publishing '
            "(design/literature-acquisition.md: the discovery decision must be in the record).",
        ]

    paper_requirements_clean = not paper_requirements_problems

    # Deposit-completeness gate (SPEC-SI-AUTHORING-001 M2, Pillar C): the ONE new RECORD-side
    # gate. Confirms the deposit carries (a) the retained deterministic record artifact
    # (located via deposit_record_path -- the M1 single source of truth, never a hard-coded
    # path) AND (b) a "Data & code availability" statement. PURE, presence-only, no LLM
    # (REQ-SA-304). ADDITIVE (REQ-SA-305): surfaced as its OWN channel below; it does NOT
    # join the `passed` exit gate, so it never weakens or replaces the existing claim-
    # reproduction / record-green audit (all_reproduced) -- the M2 exit criterion is a checker
    # that fails loud on each missing element and is additive, not a new pass/fail conjunct.
    deposit_problems = deposit_completeness_problems(deposit_record_path(run_dir))
    deposit_complete = not deposit_problems

    return VerifyReport(
        spec_id=spec.id,
        outcomes=outcomes,
        digest=record_digest(run_dir),
        all_reproduced=all_reproduced,
        paper_consistency=paper_consistency,
        paper_consistent=paper_consistent,
        paper_factrefs=paper_factrefs,
        paper_factref_clean=paper_factref_clean,
        paper_tool_vocab=paper_tool_vocab,
        paper_tool_clean=paper_tool_clean,
        paper_novelty_problems=paper_novelty_problems,
        paper_novelty_clean=paper_novelty_clean,
        paper_cross_doc_refs=paper_cross_doc_refs,
        paper_cross_doc_clean=paper_cross_doc_clean,
        paper_requirements_problems=paper_requirements_problems,
        paper_requirements_clean=paper_requirements_clean,
        paper_advisory=paper_advisory,
        deposit_problems=deposit_problems,
        deposit_complete=deposit_complete,
        passed=(
            all_reproduced
            and paper_consistent
            and paper_factref_clean
            and paper_tool_clean
            and paper_novelty_clean
            and paper_cross_doc_clean
            and paper_requirements_clean
        ),
    )


def verify_package(workspace_dir: Path) -> PackageVerifyReport:
    """The workspace-level PACKAGE gate (design/near-submission-package.md §3).

    PURE + READ-ONLY: audits the assembled ``<ws>/package/`` against the FROZEN
    ``<ws>/pkgreqs.json`` -- a deterministic, no-LLM, no-recompile umbrella over the merged
    submission. It REUSES the same pure checkers the per-run paper gates use (compile integrity,
    tool vocabulary, required sections, reference style, value fidelity) so "compiles", "names
    the science", and "re-derives from the record" mean the same thing for a package as for a
    per-run paper; it adds the package-SPECIFIC checks (layout, cite resolution, abstract limit,
    traceability tables, every listed run reproduces, README submission-readiness).

    Vacuity / posture (design §3, amended by SPEC-PAPER-GATE-001 P1, OD-1 strict + OD-8):
      - NO ``package/`` -> vacuously clean (nothing to gate; an empty workspace is fine).
      - ``package/`` present is now a CONCLUSION-BEARING artifact. A present ``package/`` with
        NO frozen ``pkgreqs.json`` is no longer a silent clean pass for the venue-FORMAT checks
        -- it is a LOUD REFUSAL naming what to freeze (REQ-PG-101/103/108). The number-audit
        (P2) ALSO runs whenever a ``package/`` exists. The venue-FORMAT sub-checks
        (required_sections / reference_style / abstract limit) still require a contract to run;
        the layout / traceability / compile / fidelity / record-green / number-audit checks run
        regardless.

    The ``record green`` check re-uses :func:`verify_run` over each run the ``run_index.csv``
    lists (the headless record audit) -- a listed run that does not reproduce fails the gate.

    Args:
        workspace_dir: the workspace root holding ``package/`` and (optionally) ``pkgreqs.json``.

    Returns:
        A :class:`PackageVerifyReport` -- inspect ``package_requirements_clean`` for the gate.
    """
    # @MX:ANCHOR: [AUTO] the single workspace-level package re-audit entry (design §3) -- the
    #   deterministic, read-only, no-LLM gate over the merged submission package.
    # @MX:REASON: [AUTO] the CLI `package`/`verify <ws>` verbs and the package test suites call
    #   this; it owns the no-LLM + read-only + reuse-the-per-run-checkers contract, and folds
    #   the per-run record audit (verify_run) in as the "record green" traceability check so a
    #   package cannot pass while a synthesized run does not reproduce.
    workspace_dir = Path(workspace_dir)
    package_dir = workspace_dir / "package"

    # No package -> nothing to gate (vacuously clean), exactly as an absent paper/ is for a run.
    if not package_dir.is_dir():
        return PackageVerifyReport(workspace_dir=workspace_dir)

    pkgreqs = _load_pkgreqs(workspace_dir)
    problems, warnings, runs, runs_reproduced = _check_package_requirements(
        workspace_dir, package_dir, pkgreqs
    )
    # The advisory channel carries the contract's body-range/free-form notes PLUS the content
    # WARNINGS (e.g. an unpublished/DOI-less citation, OD-5) -- SURFACED, never gated.
    advisory = _package_advisory(pkgreqs) + warnings
    clean = not problems
    return PackageVerifyReport(
        workspace_dir=workspace_dir,
        runs=runs,
        runs_reproduced=runs_reproduced,
        package_requirements_problems=problems,
        advisory=advisory,
        package_requirements_clean=clean,
        passed=clean,
    )


# -- per-hypothesis re-derivation (mirrors ClaimUpdater, WITHOUT persistence) --

def _audit_hypothesis(
    engine: DecisionEngine,
    hypothesis: Hypothesis,
    evidence: List[EvidenceItem],
    recorded_claim: Claim,
    *,
    strict_science: bool = False,
    negative_controls: Optional[List[EvidenceItem]] = None,
) -> VerifyOutcome:
    """Re-derive one hypothesis's EXPERIMENT belief and compare it to its recorded Claim.

    Mirrors ``ClaimUpdater._evaluate_hypothesis`` (build ``EvidenceForHypothesis`` from
    the bearings on this hypothesis, call ``engine.evaluate``, then map the verdict via
    the shared public ``status_for_verdict``) but performs NO load-or-create and NO
    persistence -- it only re-derives and compares.

    To re-derive FAITHFULLY it applies the same belief-time filters the updater does:
    proposed digitized items are EXCLUDED (figure-digitization §5), and the digitized
    self-certification gate is re-checked over the COUNTED set. A recorded binding Claim
    whose only support is a proposed / unverified / self-certified digitized item
    therefore does NOT reproduce -- the audit reports it (UNRESOLVED when there is
    nothing left to count, DIVERGED when a counted digitized fails the verifier check).

    Novelty is audited SEPARATELY (B-replace): the novelty claim ``claim-novelty-<hyp>``
    is re-derived by rule in :func:`_audit_novelty_claim`, not here -- this path is the
    EXPERIMENT claim only.
    """
    relevant = [
        ev for ev in evidence
        if any(b.target_id == hypothesis.id for b in ev.bears_on)
    ]
    # Exclude non-evidence-grade items (proposed digitized) exactly as the persister
    # does (shared ``counted_evidence``) -- a faithful re-derivation must not count what
    # the updater would not have counted.
    counted = counted_evidence(relevant)
    results = EvidenceForHypothesis(
        pairs=[
            (ev, b)
            for ev in counted
            for b in ev.bears_on
            if b.target_id == hypothesis.id
        ]
    )

    verdict = engine.evaluate(hypothesis.decision_rule, results)

    # Re-apply the digitized self-certification gate over the counted set. If a counted
    # digitized item is unverified / self-certified, the recorded Claim could not have
    # been validly derived (the updater would have HALTED) -- so the record's belief does
    # NOT follow from a properly-verified record: report DIVERGED. This is read-only (no
    # raise escapes the audit) -- the gate is consulted, not enforced as a stop.
    try:
        check_digitized_adequacy(hypothesis, counted, verdict.direction)
    except ValidityHalt as halt:
        return VerifyOutcome(
            hypothesis_id=hypothesis.id,
            recorded_status=recorded_claim.status,
            rederived_status=None,
            result=DIVERGED,
            rederived_basis=(
                "recorded claim relies on a digitized item that fails the "
                f"independent-verification gate (not reproducible from record): {halt.reason}"
            ),
        )

    # Science-guard re-check (design/science-guards.md), strict-science only + read-only
    # (no raise escapes -- the gate is CONSULTED, not enforced as a stop). Mirrors the
    # digitized re-check above: a recorded SUPPORTED formal+threshold claim whose falsifying
    # NEGATIVE_CONTROL was deleted (G3), or whose discriminating cases were dropped (G2), or
    # that was never reclassified (G1), NO LONGER re-derives under strict mode -> DIVERGED.
    # This is the tamper-evidence companion that makes the negative control part of the
    # auditable record (the guards run only in strict mode, so a lenient verify is unchanged).
    if strict_science:
        try:
            check_analyticity(hypothesis, counted, verdict.direction)
            check_discriminating_power(hypothesis, verdict.direction)
            check_falsifiability_adequacy(
                hypothesis, negative_controls or [], verdict.direction
            )
        except ValidityHalt as halt:
            return VerifyOutcome(
                hypothesis_id=hypothesis.id,
                recorded_status=recorded_claim.status,
                rederived_status=None,
                result=DIVERGED,
                rederived_basis=(
                    "recorded claim fails a science guard on re-derivation (not reproducible "
                    f"from the record under strict science): {halt.reason}"
                ),
            )

    raw_directions = {b.direction for _, b in results.pairs}
    # SINGLE source of truth (Fix 1): the SAME public derivation ClaimUpdater uses to
    # persist -- mapping + CONTESTED override -- so a faithful record re-derives exactly
    # the status that was recorded (no replayed/duplicated logic to drift).
    rederived_status = status_for_verdict(verdict, raw_directions)

    result = _classify(verdict.direction, rederived_status, recorded_claim.status)
    return VerifyOutcome(
        hypothesis_id=hypothesis.id,
        recorded_status=recorded_claim.status,
        rederived_status=rederived_status,
        result=result,
        rederived_basis=verdict.confidence.basis,
    )


def _classify(
    direction: BearingDirection,
    rederived_status: ClaimStatus,
    recorded_status: ClaimStatus,
) -> str:
    """REPRODUCED / DIVERGED / UNRESOLVED for one hypothesis.

    UNRESOLVED is decided by the re-derived *direction* being ``inconclusive`` (the F2
    "no recorded trail / cannot re-derive" outcome for a non-numeric rule), reported
    distinctly even when the recorded claim is also PROPOSED -- because "the record
    does not let me re-derive this belief" is a different audit finding from "I
    re-derived the same belief". An inconclusive re-derivation is never REPRODUCED, so
    it fails the CI gate. Any non-inconclusive mismatch is DIVERGED.
    """
    if direction == BearingDirection.INCONCLUSIVE:
        return UNRESOLVED
    return REPRODUCED if rederived_status == recorded_status else DIVERGED


def _is_novelty_claim(claim: Claim) -> bool:
    """True iff ``claim`` is a novelty claim (id ``claim-novelty-{result,method}-<hyp>``).

    Both 2-kind ids share the ``claim-novelty-`` prefix, so this prefix test still
    identifies a novelty claim of either kind. The specific kind is parsed by
    :func:`_novelty_kind_of`.
    """
    return claim.id.startswith("claim-novelty-")


def _novelty_kind_of(claim: Claim) -> Literal["result", "method"]:
    """Parse the novelty kind from a novelty claim id (``claim-novelty-{kind}-<hyp>``).

    Strips the ``claim-novelty-`` prefix and reads the kind token. Robust when the
    hypothesis id itself contains hyphens (the remainder is matched by its leading
    ``result-`` / ``method-`` token only). Precondition: ``_is_novelty_claim(claim)`` --
    a non-novelty id raises (the caller gates on ``_is_novelty_claim`` first).

    Raises:
        ValueError: if the id is not a recognised 2-kind novelty id.
    """
    remainder = claim.id[len("claim-novelty-"):]
    if remainder.startswith("result-"):
        return "result"
    if remainder.startswith("method-"):
        return "method"
    raise ValueError(
        f"unrecognised novelty claim id '{claim.id}': expected "
        "claim-novelty-result-<hyp> or claim-novelty-method-<hyp> (2-kind)"
    )


def _audit_novelty_claim(
    hypothesis: Hypothesis,
    kind: Literal["result", "method"],
    recorded_claim: Claim,
    novelty_decisions: List[EvidenceItem],
) -> VerifyOutcome:
    """Re-derive one {hypothesis, kind} novelty claim status by RULE and compare to the
    recorded one (2-kind).

    B-replace (design/literature-acquisition.md): the novelty claim is rule-derived
    (``derive_novelty_status(hyp, kind, ...)`` over the recorded NOVELTY_DECISIONs of that
    kind), decoupled from the experiment verdict. A recorded SUPPORTED novelty claim is
    faithful only if the record still holds a *found_nothing* decision for THIS {hyp,
    kind}; if that decision was deleted (or a found_something was tampered to found_nothing,
    or the only found_nothing was bound to the OTHER kind), the re-derived status diverges
    from the recorded one. READ-ONLY: no persist, no LLM.

    Classification: matching status -> REPRODUCED; any mismatch -> DIVERGED (novelty has
    no inconclusive/UNRESOLVED state -- the rule always yields PROPOSED or SUPPORTED).
    """
    rederived = derive_novelty_status(hypothesis, kind, novelty_decisions)
    result = REPRODUCED if rederived == recorded_claim.status else DIVERGED
    basis = (
        f"{kind}-novelty re-derived from the recorded prior-art decisions"
        if result == REPRODUCED
        else (
            f"recorded {kind}-novelty claim does not re-derive from the record: recorded "
            f"{recorded_claim.status.value}, re-derived {rederived.value} (a "
            f"found_nothing {kind} prior-art decision was deleted or tampered)"
        )
    )
    return VerifyOutcome(
        hypothesis_id=hypothesis.id,
        recorded_status=recorded_claim.status,
        rederived_status=rederived,
        result=result,
        rederived_basis=basis,
    )


# -- read-only paper-consistency check (Phase 3, D4) -------------------------

def _check_paper_consistency(run_dir: Path) -> Dict[str, LatexRefReport]:
    """Re-check each rendered paper document's internal ``\\ref``<->``\\label`` integrity.

    READ-ONLY: reads ``run_dir/paper/<doc>.tex`` for each of ``_PAPER_DOCS`` that EXISTS
    and runs the pure :func:`check_latex_ref_consistency` over it. No recompile, no LLM,
    no write -- this is the same headless, third-party spirit as the claim re-derivation.

    Returns a map keyed by file name (``draft.tex`` / ``si.tex``) -> its
    :class:`LatexRefReport`. EMPTY when the run has no ``paper/`` directory or neither
    document is present -- the caller treats an empty map as "nothing to gate" (vacuously
    consistent), preserving the pre-Phase-3 exit behavior for runs without a paper.
    """
    paper_dir = run_dir / "paper"
    reports: Dict[str, LatexRefReport] = {}
    if not paper_dir.is_dir():
        return reports
    for name in _PAPER_DOCS:
        doc = paper_dir / name
        if doc.is_file():
            reports[name] = check_latex_ref_consistency(
                doc.read_text(encoding="utf-8")
            )
    return reports


def _check_cross_doc_refs(run_dir: Path) -> List[str]:
    """Gate the MAIN paper's plain-text "Figure/Table S<n>" citations against the SI.

    READ-ONLY (mirrors :func:`_check_paper_consistency`): reads ``run_dir/paper/draft.tex``
    and ``run_dir/paper/si.tex`` and runs the pure :func:`check_cross_doc_s_refs`. The
    cross-document relationship needs BOTH documents, so the gate is vacuous (returns ``[]``)
    unless both are present -- consistent with the per-document checks skipping an absent
    file, and avoiding a false dangling on a single-document run (the within-run compiler
    always emits draft.tex and si.tex together). Returns the dangling "Figure/Table S<n>"
    citations (empty = clean / a document missing).
    """
    paper_dir = run_dir / "paper"
    draft = paper_dir / "draft.tex"
    si = paper_dir / "si.tex"
    if not (draft.is_file() and si.is_file()):
        return []
    report = check_cross_doc_s_refs(
        draft.read_text(encoding="utf-8"), si.read_text(encoding="utf-8")
    )
    return report.unresolved_refs


def _check_paper_factrefs(run_dir: Path) -> Dict[str, List[str]]:
    """Re-scan each rendered paper document for RESIDUAL ``\\evval``/``\\status`` macros.

    READ-ONLY (mirrors :func:`_check_paper_consistency`): a rendered ``.tex`` should carry
    NONE -- :func:`sci_adk.render.factref.substitute_factrefs` substitutes every fidelity
    macro at render time -- so a residual is a fidelity divergence (substitution bypassed /
    the .tex hand-edited). Returns a map keyed by file name -> the residual macros found
    (only for documents that have any); an empty map means clean / no paper.
    """
    paper_dir = run_dir / "paper"
    residuals: Dict[str, List[str]] = {}
    if not paper_dir.is_dir():
        return residuals
    for name in _PAPER_DOCS:
        doc = paper_dir / name
        if doc.is_file():
            found = find_unresolved_factrefs(doc.read_text(encoding="utf-8"))
            if found:
                residuals[name] = found
    return residuals


def _check_paper_novelty(
    run_dir: Path, spec: Spec, novelty_decisions: List[EvidenceItem]
) -> Dict[str, List[str]]:
    """Re-derive every ``\\novelty{kind}{hyp}{...}`` assertion in each paper document (N3).

    READ-ONLY (mirrors :func:`_check_paper_factrefs`): reads ``run_dir/paper/<doc>.tex`` for
    each of ``_PAPER_DOCS`` that EXISTS and re-runs the SAME record re-derivation the
    renderer did (:func:`sci_adk.render.novelty.find_unsupported_novelty`, which re-derives
    via ``derive_novelty_status`` -- the single source of truth, NOT the recorded claim). A
    document with an unsupported / unknown-hyp / bad-kind novelty assertion (e.g. the backing
    ``found_nothing`` decision was deleted) yields its problem lines; a fully-supported (or
    novelty-free) document yields none. Returns a map keyed by file name -> the problems
    (only for documents that have any); an empty map means clean / no paper.

    BOTH ``draft.tex`` and ``si.tex`` are scanned -- there is no gap where an author could
    sneak ``\\novelty`` into SI prose to dodge the gate (the SI also runs the N2 render gate).
    """
    paper_dir = run_dir / "paper"
    problems: Dict[str, List[str]] = {}
    if not paper_dir.is_dir():
        return problems
    for name in _PAPER_DOCS:
        doc = paper_dir / name
        if doc.is_file():
            found = find_unsupported_novelty(
                doc.read_text(encoding="utf-8"), spec, novelty_decisions
            )
            if found:
                problems[name] = found
    return problems


def _check_paper_tool_vocab(run_dir: Path) -> List[str]:
    """Re-scan the SUBMISSION documents for §10 tool-vocabulary leaks (READ-ONLY).

    SPEC-SI-AUTHORING-001 REQ-SA-204 (AC-B4): under the authoring flow ``si.tex`` is a
    SUBMISSION belief document (the authored overflow of ``draft.tex``), so the per-run
    tool-vocab gate scans BOTH ``draft.tex`` AND ``si.tex`` -- the same documents the
    package-path gate already covers (``verify.py`` package scan). Previously only
    ``draft.tex`` was scanned and ``si.tex`` was exempt; that exemption is now lifted.

    The deposit's deterministic ``record.tex`` (REQ-SA-206 / AC-B6) is NOT scanned: it is
    the record/provenance and legitimately names ``capability:``/``docker:``/
    ``environment:``. It lives OUTSIDE ``paper/`` (only ``_PAPER_DOCS`` under ``paper/``
    are scanned), so the exemption holds BY CONSTRUCTION -- the boundary cannot invert.

    Returns the distinct forbidden terms found across the submission documents (empty =
    clean / no submission docs), via the pure
    :func:`sci_adk.render.paper.check_paper_tool_vocabulary`.
    """
    paper_dir = run_dir / "paper"
    leaks: List[str] = []
    for name in _PAPER_DOCS:
        doc = paper_dir / name
        if doc.is_file():
            for term in check_paper_tool_vocabulary(doc.read_text(encoding="utf-8")):
                if term not in leaks:
                    leaks.append(term)
    return leaks


# -- F1 publishing-requirements gate (design §1.3) ---------------------------

def _check_paper_requirements(
    run_dir: Path,
    evidence: List[EvidenceItem],
    claims: Optional[List[Claim]] = None,
    spec: Optional[Spec] = None,
) -> tuple[List[str], List[str]]:
    """Run the deterministic checks the FROZEN ``pubreqs.json`` declares (F1, design §1.3).

    READ-ONLY (mirrors the other ``_check_paper_*`` helpers): reads ``run_dir/pubreqs.json``
    (the frozen publishing contract), ``run_dir/paper/draft.tex``, the co-located rasters, and
    ``run_dir/paper/reproduce.py`` -- never recompiles, never writes, never calls an LLM. Runs
    ONLY the requirements the contract turns on, and returns ``(problems, warnings)`` -- the FAIL
    lines (empty = clean, gated via ``paper_requirements_clean``) and the NON-BLOCKING advisory
    lines (SPEC-PAPER-GATE-001 OD-5 unpublished/DOI-less citation + OD-6 undeclared-order;
    surfaced via ``paper_advisory``, NEVER gated -- the per-run companion to the package gate's
    advisory channel).

    SPEC-PAPER-GATE-001 P1+P2 (the non-vacuous posture, OD-1 strict + OD-8 immediate):
      - A run with NO ``paper/draft.tex`` is NOT a conclusion-bearing artifact -> this stays
        vacuously clean exactly as before (every pre-paper run is unchanged).
      - A run WITH a ``paper/draft.tex`` IS conclusion-bearing. An absent ``pubreqs.json`` is
        no longer a silent clean pass -- it is a LOUD, actionable REFUSAL (REQ-PG-101/108)
        naming the missing contract and what to run to freeze it. With the contract present,
        the P2 number-audit ALSO runs: every quantitative token in draft.tex + si.tex must
        trace to the recorded-value pool (Claim statistics + Evidence scalars), else FAIL
        (REQ-PG-201/202). This is ADDITIVE -- it never touches the claim-reproduction gate
        (REQ-PG-107).

    ADVISORY items and ``max_pages`` are NEVER gated here (no deterministic page count exists
    without a compile); the CLI surfaces them separately.

    The contract-declared checks (design §1.3 table), each guarded by its field:
      - required_sections -> each named ``\\section{...}`` present in draft.tex;
      - figure_font_policy -> the F2 font preamble present for a figure-bearing draft;
      - image_min_dpi      -> every raster ``\\includegraphics`` >= the threshold DPI;
      - reference_style    -> the declared bib style wired in draft.tex;
      - max_words          -> the prose word count within the limit;
      - reproduction_bundle -> ``paper/reproduce.py`` present + referencing recorded
        ``code_ref``s (FAIL-OPEN for a pointer-only bundle, design §6 OF-4 -- see
        :func:`_reproduction_bundle_problems`).
    """
    draft = run_dir / "paper" / "draft.tex"
    draft_tex = draft.read_text(encoding="utf-8") if draft.is_file() else ""

    # OD-1 strict conclusion-bearing trigger (per-run): ANY paper/draft.tex. A run with no
    # draft.tex declared no paper -> vacuously clean (backward compatible, EC-1 spirit).
    if not draft.is_file():
        return [], []

    pubreqs_path = run_dir / "pubreqs.json"
    if not pubreqs_path.is_file():
        # OD-8 IMMEDIATE refusal: a conclusion-bearing draft with no frozen contract is NOT a
        # silent clean pass. Name what to freeze (REQ-PG-101/108) -- actionable, not a flip.
        return [
            "publishing contract: paper/draft.tex is conclusion-bearing but no frozen "
            "pubreqs.json exists -- run `sci-adk pubreqs freeze <run>` to freeze the "
            "publishing contract before verify can pass (SPEC-PAPER-GATE-001 P1)"
        ], []

    pubreqs = PubReqs.model_validate(
        json.loads(pubreqs_path.read_text(encoding="utf-8"))
    )

    problems: List[str] = []
    warnings: List[str] = []

    # P2 number-audit (REQ-PG-201/202/204): every quantitative token in draft.tex + si.tex
    # traces to the recorded-value pool (Claim statistics + Evidence scalars). Compares ONLY
    # against recorded values (record vs belief, REQ-PG-203).
    pool = pool_from_record(claims or [], evidence, spec)
    for name in _PAPER_DOCS:
        doc = run_dir / "paper" / name
        if doc.is_file():
            problems.extend(
                number_audit_problems(doc.read_text(encoding="utf-8"), pool, source=name)
            )

    if pubreqs.required_sections:
        problems.extend(
            f"missing required section: {name}"
            for name in required_sections_problems(draft_tex, pubreqs.required_sections)
        )
        # P4 (REQ-PG-401/402): section ORDER against the DECLARED order (the required_sections
        # list order is the declared order) -> FAIL on deviation (OD-6: declared order = FAIL).
        problems.extend(section_order_problems(draft_tex, pubreqs.required_sections))
    else:
        # OD-6: no order declared -> WARN against the default IMRaD order (non-blocking, routed
        # to the per-run advisory channel) -- never a FAIL when nothing was declared. Mirrors the
        # package gate's undeclared-order branch.
        warnings.extend(
            section_order_problems(draft_tex, list(PUB_DEFAULT_REQUIRED_SECTIONS))
        )

    if pubreqs.figure_font_policy:
        problems.extend(figure_font_policy_problems(draft_tex))

    if pubreqs.image_min_dpi is not None:
        figures_dir = run_dir / "paper" / "figures"
        problems.extend(
            image_dpi_problems(draft_tex, figures_dir, pubreqs.image_min_dpi)
        )

    if pubreqs.reference_style:
        problems.extend(
            reference_style_problems(draft_tex, pubreqs.reference_style)
        )

    problems.extend(max_words_problems(draft_tex, pubreqs.max_words))

    # P3 (REQ-PG-301/302/303/305): citation gates over the per-run paper. Load the per-run bib
    # (paper/references.bib). cite-resolution closes the per-run gap (REQ-PG-305 -- the package
    # already had it); the shape + disambiguation gates validate every \cite/.bib key against
    # <Surname><Year>(+a/b) (OD-4: FAIL, never re-key). The unpublished/DOI-less WARNING
    # (REQ-PG-304, OD-5) routes to the per-run advisory channel (non-gating) -- it was
    # package-scoped before R1 added a per-run advisory channel.
    bib_path = run_dir / "paper" / "references.bib"
    bib = bib_path.read_text(encoding="utf-8") if bib_path.is_file() else ""
    problems.extend(cite_resolution_problems(draft_tex, bib))
    problems.extend(citation_key_shape_problems(draft_tex, bib))
    problems.extend(citation_disambiguation_problems(draft_tex, bib))
    problems.extend(bib_latex_safety_problems(bib))
    warnings.extend(unpublished_citation_warnings(draft_tex, bib))

    # SPEC-SI-AUTHORING-001 M6 (REQ-SA-611/612/614): the authored si.tex has its OWN
    # references_SI.bib -- ADD the parallel cite-resolution gate for it, REUSING the same
    # pure cite_resolution_problems checker. Every \cite* key in si.tex must resolve in
    # references_SI.bib; a dangling SI cite FAILS naming the key. A thin/absent SI or a
    # citation-free one is vacuously clean (no keys -> no problems, REQ-SA-615).
    si_tex_path = run_dir / "paper" / "si.tex"
    if si_tex_path.is_file():
        si_bib_path = run_dir / "paper" / "references_SI.bib"
        si_bib = si_bib_path.read_text(encoding="utf-8") if si_bib_path.is_file() else ""
        problems.extend(cite_resolution_problems(si_tex_path.read_text(encoding="utf-8"), si_bib))

    # SPEC-SI-AUTHORING-001 M6 hardening: BOTH bib files must be brace-balanced (integrity). The
    # cite gates prove citations RESOLVE; this fail-loud gate proves the .bib actually COMPILES
    # -- a brace-unbalanced entry is a hard LaTeX error the cite gate misses (bib_keys reads
    # only the first line). BOTH references.bib (main) AND references_SI.bib (SI) are validated
    # (the user's "_SI도 따로 있기에 둘 다 검정" requirement), naming the offending file. A MISSING
    # bib is NOT a failure (thin/absent SI, no-pool run stay clean, REQ-SA-606/615); only a
    # PRESENT-but-malformed bib fails. REUSE the existing _braces_balanced helper (no new balancer).
    for _bib_name in ("references.bib", "references_SI.bib"):
        _bib_file = run_dir / "paper" / _bib_name
        if _bib_file.is_file() and not _braces_balanced(
            _bib_file.read_text(encoding="utf-8")
        ):
            problems.append(f"bib integrity: {_bib_name} has unbalanced braces")

    if pubreqs.reproduction_bundle:
        problems.extend(_reproduction_bundle_problems(run_dir, evidence))

    return problems, warnings


# Process/decision meta-records carry a decision pointer in ``code_ref`` (e.g.
# ``prior_work:searched``), NOT generating code to reproduce, and hold ``bears_on=[]``.
# They must never enter the reproduction-bundle requirement: reproduction is about the
# GENERATING code, and requiring an already-rendered ``reproduce.py`` to reference a
# decision ref recorded AFTER render would break verify the moment a user honestly records
# prior work / novelty / a contested decision (the field-report P3 trap).
_NON_REPRODUCIBLE_KINDS = frozenset(
    {
        EvidenceKind.PRIOR_WORK_DECISION,
        EvidenceKind.NOVELTY_DECISION,
        EvidenceKind.CONTESTED_RECORD,
    }
)


def _reproduction_bundle_problems(
    run_dir: Path, evidence: List[EvidenceItem]
) -> List[str]:
    """The F3 reproduction-bundle gate (design §3.3 reconciled with §6 OF-4), READ-ONLY.

    Reconciling §3.3 ("``paper/reproduce.py`` + ``paper/code/`` exist, are non-empty, and
    reference real recorded ``code_ref``s") with §6 OF-4 (a pointer-only bundle is FAIL-OPEN --
    a bare-commit ``code_ref`` with no co-located script does NOT block the gate), the EXACT
    semantics this gate implements -- grounded in what the compiler actually emits
    (loop/compiler.py ``_emit_reproduction_bundle``) -- are:

      1. ``paper/reproduce.py`` MUST EXIST and be non-empty. The compiler writes it whenever
         ANY Evidence item carries a ``code_ref`` (scripts OR pure pointers). A contract that
         declares ``reproduction_bundle`` but whose run has at least one ``code_ref`` yet no
         ``reproduce.py`` is a real failure (the bundle was declared but not produced / was
         hand-deleted).

      2. ``reproduce.py`` MUST reference the REAL recorded ``code_ref``s. The driver embeds
         every ``code_ref`` it was built from (in its ``SCRIPTS`` / ``POINTERS`` lists -- see
         render/reproduction.render_reproduce_driver), so the gate confirms each ``code_ref``
         recorded in the Evidence appears in the driver text. A ``reproduce.py`` that omits a
         recorded ``code_ref`` references a bundle out of sync with the record (fail).

      3. ``paper/code/`` is required NON-EMPTY ONLY when the run has RESOLVABLE SCRIPTS. The
         compiler writes ``paper/code/`` only when at least one ``code_ref`` resolved to a
         co-located script; a POINTER-ONLY run (an all-pointer run: bare git hashes, no
         co-located scripts) honestly writes NO ``paper/code/`` dir. OF-4 (fail-open) wins over
         §3.3's literal "non-empty": we CANNOT require ``paper/code/`` for an all-pointer
         bundle -- the gate must PASS for an honest pointer-only ``reproduce.py``. We therefore
         do NOT inspect ``paper/code/`` directly: requirement (2) already proves the driver
         references the real refs, and whether a ref resolved to a script vs a pointer is the
         compiler's fail-open decision, not a gate condition. (We never re-resolve paths or
         execute code -- running recorded code inside the read-only verify gate is out of
         scope and unsafe, design §3.3.)

    The set of recorded ``code_ref``s is read from the Evidence log (the same list verify
    already loaded). A run with NO ``code_ref`` at all (the compiler writes no bundle) but a
    contract that declares ``reproduction_bundle`` is a real failure: the contract asked for a
    bundle the record cannot back -- the absent ``reproduce.py`` is reported.

    Returns the failure lines (empty = the bundle satisfies the contract).
    """
    recorded_refs = sorted(
        {
            ref
            for ev in evidence
            if ev.kind not in _NON_REPRODUCIBLE_KINDS
            and (ref := (ev.provenance.code_ref or "").strip())
        }
    )

    reproduce = run_dir / "paper" / "reproduce.py"
    if not reproduce.is_file():
        if recorded_refs:
            return [
                "reproduction bundle: paper/reproduce.py is missing, but the record holds "
                f"{len(recorded_refs)} code_ref(s) to reproduce from"
            ]
        return [
            "reproduction bundle: declared, but paper/reproduce.py is missing and the "
            "record holds no code_ref to build it from"
        ]

    driver = reproduce.read_text(encoding="utf-8")
    if not driver.strip():
        return ["reproduction bundle: paper/reproduce.py is present but empty"]

    # The driver must reference each recorded code_ref (it embeds them in SCRIPTS/POINTERS).
    missing_refs = [ref for ref in recorded_refs if ref not in driver]
    if missing_refs:
        return [
            "reproduction bundle: paper/reproduce.py does not reference recorded "
            f"code_ref(s): {', '.join(missing_refs)}"
        ]
    return []


# -- package-requirements gate (design/near-submission-package.md §3) --------

def _load_pkgreqs(workspace_dir: Path) -> Optional[PackageReqs]:
    """Load the FROZEN ``<ws>/pkgreqs.json`` package contract, or None if absent (read-only).

    Absent -> None (the venue-FORMAT sub-checks are vacuously clean; the layout/traceability
    checks still run). A malformed contract re-raises as a ValueError (verify surfaces it).
    """
    pkgreqs_path = workspace_dir / "pkgreqs.json"
    if not pkgreqs_path.is_file():
        return None
    return PackageReqs.model_validate(
        json.loads(pkgreqs_path.read_text(encoding="utf-8"))
    )


def _package_advisory(pkgreqs: Optional[PackageReqs]) -> List[str]:
    """The contract's free-form ADVISORY items (design §3), SURFACED in the report, NEVER gated.

    Returns the human-readable advisory lines (empty when no contract / nothing advisory).
    NOTE: ``body_word_range`` is no longer advisory -- SPEC-PAPER-GATE-001 P4 / AC-3 makes it
    GATE (:func:`body_word_range_problems`), so it is not surfaced here as a note any more.
    """
    if pkgreqs is None:
        return []
    return list(pkgreqs.advisory)


def _read_package_doc(package_dir: Path, name: str) -> str:
    """Read ``package/01_manuscript/<name>`` (or '' if absent), read-only."""
    doc = package_dir / "01_manuscript" / name
    return doc.read_text(encoding="utf-8") if doc.is_file() else ""


def _run_index_runs(package_dir: Path) -> Optional[List[str]]:
    """The run ids listed in ``06_provenance/run_index.csv`` (read-only), or None if absent.

    PURE-ish: parses the CSV's ``run_id`` column. Returns ``[]`` for a present-but-empty index
    (header only) and ``None`` when the file is absent (the traceability gate distinguishes
    "no run index" from "an index listing zero runs").
    """
    idx = package_dir / "06_provenance" / "run_index.csv"
    if not idx.is_file():
        return None
    import csv

    runs: List[str] = []
    with idx.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            rid = (row.get("run_id") or "").strip()
            if rid:
                runs.append(rid)
    return runs


def _check_package_requirements(
    workspace_dir: Path,
    package_dir: Path,
    pkgreqs: Optional[PackageReqs],
) -> tuple[List[str], List[str], List[str], Dict[str, bool]]:
    """Run the deterministic PACKAGE checks (design §3), READ-ONLY, no recompile, no LLM.

    REUSES the per-run pure checkers (compile integrity, tool vocabulary, required sections,
    reference style, value fidelity) so the package and per-run gates share one definition of
    "compiles" / "names the science" / "re-derives", and adds the package-SPECIFIC checks
    (layout, cite resolution, abstract limit, traceability tables, every listed run reproduces,
    README submission-readiness). The venue-FORMAT checks (required_sections / reference_style /
    abstract limit) run ONLY when ``pkgreqs`` declares them (absent contract -> vacuously clean
    for those, design §3); the layout / compile / traceability / fidelity / record-green checks
    run regardless (a ``package/`` exists, so they are meaningful).

    Returns ``(problems, warnings, runs, runs_reproduced)`` -- the failure lines (empty = clean),
    the NON-BLOCKING warnings (surfaced via the report advisory, never gated -- e.g. an
    unpublished/DOI-less citation per OD-5), the run ids the run_index lists, and each listed
    run's REPRODUCED flag.
    """
    problems: List[str] = []
    warnings: List[str] = []
    manuscript_dir = package_dir / "01_manuscript"

    main_tex = _read_package_doc(package_dir, _PACKAGE_MAIN)
    si_tex = _read_package_doc(package_dir, _PACKAGE_SI)
    bib = ""
    bib_path = manuscript_dir / "references.bib"
    if bib_path.is_file():
        bib = bib_path.read_text(encoding="utf-8")

    # SPEC-PAPER-GATE-001 P1 (OD-1 strict + OD-8 immediate): a package/ that exists at all is a
    # conclusion-bearing artifact. An absent frozen pkgreqs.json is NOT a silent clean pass --
    # it is a LOUD, actionable REFUSAL naming what to freeze (REQ-PG-101/103/108). This is
    # additive; the layout/traceability/fidelity/record-green checks below still run.
    if pkgreqs is None:
        problems.append(
            "package contract: package/ is conclusion-bearing but no frozen pkgreqs.json "
            "exists -- run `sci-adk pkgreqs freeze <workspace>` to freeze the package "
            "contract before verify can pass (SPEC-PAPER-GATE-001 P1)"
        )

    # SPEC-PAPER-GATE-001 P2 (REQ-PG-201/202/204): every quantitative token in main.tex + si.tex
    # must trace to the package's recorded-value pool -- the union of the record CSVs the
    # manuscript dumps from (02_data/*.csv data tables + 06_provenance/run_index.csv run-index
    # counts, via from_package). Compares ONLY against recorded values (record vs belief,
    # REQ-PG-203). Runs whenever a package/ exists -- the merged manuscript is the central leak
    # (L2/L3: hand-typed prose) this gate closes.
    # stage ii (OD-2): exact-only here (allow_derived=False). The package pool is the BROAD
    # record dump (often hundreds of cells), where the per-run derived policy's O(N^2) operand
    # combinations are dense enough to admit a coincidentally-matching wrong number; a derived
    # quantity must instead have a recorded home (pulled via a record macro). The per-run audit
    # keeps the derived policy (its pool is small + curated -- see _check_paper_requirements).
    pool = RecordedValuePool.from_package(package_dir)
    for name, tex in ((_PACKAGE_MAIN, main_tex), (_PACKAGE_SI, si_tex)):
        if tex:
            problems.extend(
                number_audit_problems(tex, pool, source=name, allow_derived=False)
            )

    # 1. Layout: the 6 folders + MANIFEST.md + README.md present.
    problems.extend(layout_problems(package_dir))

    # 2. Compile integrity: main.tex + si.tex \ref<->\label, figure presence, braces.
    for name, tex in ((_PACKAGE_MAIN, main_tex), (_PACKAGE_SI, si_tex)):
        if not tex:
            problems.append(f"package manuscript: 01_manuscript/{name} is missing or empty")
            continue
        report = check_latex_ref_consistency(tex)
        for ref in report.unresolved_refs:
            problems.append(f"compile integrity: {name} has an unresolved \\ref{{{ref}}}")
        for label in report.duplicate_labels:
            problems.append(f"compile integrity: {name} has a duplicate \\label{{{label}}}")
        if not _braces_balanced(tex):
            problems.append(f"compile integrity: {name} has unbalanced braces")
    # main.tex figures must resolve to co-located files (the manuscript's figures/ dir).
    if main_tex:
        problems.extend(figure_presence_problems(main_tex, manuscript_dir))

    # 3. Citations wired: every \cite* key in main.tex resolves in references.bib. P3
    #    (REQ-PG-301/302/303): the shape + disambiguation gates validate every \cite/.bib key
    #    against <Surname><Year>(+a/b) (OD-4: FAIL, never re-key). The unpublished/DOI-less
    #    citation is a non-blocking WARNING (REQ-PG-304, OD-5) routed to the advisory channel.
    if main_tex:
        problems.extend(cite_resolution_problems(main_tex, bib))
        problems.extend(citation_key_shape_problems(main_tex, bib))
        problems.extend(citation_disambiguation_problems(main_tex, bib))
        problems.extend(bib_latex_safety_problems(bib))
        warnings.extend(unpublished_citation_warnings(main_tex, bib))

    # SPEC-SI-AUTHORING-001 M6 (REQ-SA-613/614): the authored package si.tex has its OWN
    # 01_manuscript/references_SI.bib -- ADD the parallel cite-resolution gate, REUSING the
    # same pure cite_resolution_problems checker. Every \cite* key in si.tex must resolve in
    # references_SI.bib; a dangling package SI cite FAILS naming the key. A thin/citation-free
    # SI is vacuously clean (REQ-SA-615). Independent of main.tex's references.bib.
    if si_tex:
        si_bib = ""
        si_bib_path = manuscript_dir / _REFERENCES_SI_BIB
        if si_bib_path.is_file():
            si_bib = si_bib_path.read_text(encoding="utf-8")
        problems.extend(cite_resolution_problems(si_tex, si_bib))

    # SPEC-SI-AUTHORING-001 M6 hardening: BOTH package bib files must be brace-balanced. Symmetric
    # to the per-run gate -- the cite gates prove citations RESOLVE, this fail-loud gate proves the
    # .bib actually COMPILES (a brace-unbalanced entry is a hard LaTeX error the cite gate misses).
    # BOTH 01_manuscript/references.bib (main) AND references_SI.bib (SI) are validated (둘 다 검정),
    # naming the offending file; a MISSING bib is not a failure. REUSE _braces_balanced.
    for _bib_name in ("references.bib", _REFERENCES_SI_BIB):
        _bib_file = manuscript_dir / _bib_name
        if _bib_file.is_file() and not _braces_balanced(
            _bib_file.read_text(encoding="utf-8")
        ):
            problems.append(f"bib integrity: {_bib_name} has unbalanced braces")

    # 4. Tool-agnostic: main.tex + si.tex carry no toolchain noun. SPEC-SI-AUTHORING-001 M5
    #    (REQ-SA-507): the package si.tex is now AUTHORED belief (a sibling of main.tex), so the
    #    gate legitimately polices BOTH manuscript documents tool-agnostic (the merged submission
    #    reads as science end to end) -- REUSE the per-run paper checker. The deterministic record
    #    relocated OUT of this dir to 06_provenance/record.tex and is EXEMPT BY CONSTRUCTION (the
    #    gate reads only 01_manuscript/), so it may legitimately name provenance.
    for name, tex in ((_PACKAGE_MAIN, main_tex), (_PACKAGE_SI, si_tex)):
        leaks = check_paper_tool_vocabulary(tex) if tex else []
        if leaks:
            problems.append(
                f"tool-vocabulary: {name} names the toolchain, not the science: "
                + ", ".join(leaks)
            )

    # 5. Value fidelity: no residual \evval/\status fact macro in main.tex/si.tex (REUSE the
    #    reframe gate -- a residual means substitution was bypassed / the .tex was hand-edited).
    for name, tex in ((_PACKAGE_MAIN, main_tex), (_PACKAGE_SI, si_tex)):
        residuals = find_unresolved_factrefs(tex) if tex else []
        if residuals:
            problems.append(
                f"value fidelity: {name} carries unsubstituted fact macro(s): "
                + ", ".join(residuals)
            )

    # 6. Venue-FORMAT checks (only when the contract declares them). The F2 font-policy +
    #    raster-DPI checks (SPEC-PAPER-GATE-001 REQ-PG-106) REUSE the per-run pure checkers so
    #    the package and per-run gates apply ONE definition of the F2 policy (closing the F2
    #    wiring gap). The package figures live at 01_manuscript/figures/ (the assembler's
    #    co-located dir), so the DPI checker resolves rasters there.
    if pkgreqs is not None and main_tex:
        if pkgreqs.required_sections:
            problems.extend(
                f"missing required section: {sec}"
                for sec in required_sections_problems(main_tex, pkgreqs.required_sections)
            )
            # P4 (REQ-PG-401/402, OD-6): a DECLARED order (required_sections) -> FAIL on deviation.
            problems.extend(section_order_problems(main_tex, pkgreqs.required_sections))
        else:
            # OD-6: no order declared -> WARN against the default IMRaD order (non-blocking,
            # routed to the advisory channel) -- never a FAIL when nothing was declared.
            warnings.extend(
                section_order_problems(main_tex, list(PKG_DEFAULT_REQUIRED_SECTIONS))
            )
        if pkgreqs.figure_font_policy:
            problems.extend(figure_font_policy_problems(main_tex))
        if pkgreqs.image_min_dpi is not None:
            problems.extend(
                image_dpi_problems(
                    main_tex, manuscript_dir / "figures", pkgreqs.image_min_dpi
                )
            )
        if pkgreqs.reference_style:
            problems.extend(
                reference_style_problems(main_tex, pkgreqs.reference_style)
            )
        problems.extend(
            abstract_max_words_problems(main_tex, pkgreqs.abstract_max_words)
        )
        # P4 (REQ-PG-404 / AC-3): the body word range now GATES (was advisory) -- a body outside
        # the declared (min, max) FAILS, via P1's non-vacuous posture.
        problems.extend(
            body_word_range_problems(main_tex, pkgreqs.body_word_range)
        )

    # 7. Traceability + record green: claims_all.csv + run_index.csv present, every listed run
    #    reproduces (REUSE verify_run -- the headless record audit).
    runs, runs_reproduced, traceability_problems = _check_package_traceability(
        workspace_dir, package_dir
    )
    problems.extend(traceability_problems)

    # 8. README submission-readiness section present.
    readme = package_dir / "README.md"
    if readme.is_file():
        problems.extend(
            readme_submission_readiness_problems(readme.read_text(encoding="utf-8"))
        )
    # (a missing README.md is already reported by layout_problems; do not double-report)

    # 9. Deposit-completeness (SPEC-SI-AUTHORING-001 M5, Pillar E / REQ-SA-508): REUSE the M2
    #    `deposit_completeness_problems` checker, pointed at the package record path via the
    #    single source `package_record_path` (symmetric to per-run `deposit_record_path`, never
    #    a hard-coded path). It confirms the package carries (a) the relocated record artifact
    #    `06_provenance/record.tex` AND (b) a "Data & code availability" statement IN THAT RECORD
    #    BODY (REQ-SA-506a, the authoritative source -- NOT the README). PURE, presence-only, no
    #    LLM (REQ-SA-511); reports ONE problem at a time (record-missing first, REQ-SA-509).
    #    F3 (INTENDED asymmetry): UNLIKE per-run M2 (a separate non-gating channel), this APPENDS
    #    to the package `problems`, so the package path's `clean = not problems` / `passed = clean`
    #    makes it a HARD gate -- a package is the final submission unit (REQ-SA-510).
    problems.extend(deposit_completeness_problems(package_record_path(package_dir)))

    return problems, warnings, runs, runs_reproduced


def _braces_balanced(tex: str) -> bool:
    """True iff ``tex`` has equal ``{`` and ``}`` counts (the package self-check's brace rule).

    The same coarse balance test ``check_package.py`` uses -- a deterministic compile-integrity
    signal (an unbalanced brace is a hard LaTeX error), not a full TeX parse.
    """
    return tex.count("{") == tex.count("}")


def _check_package_traceability(
    workspace_dir: Path, package_dir: Path
) -> tuple[List[str], Dict[str, bool], List[str]]:
    """The traceability + record-green checks (design §3), READ-ONLY.

    Confirms ``02_data/claims_all.csv`` + ``06_provenance/run_index.csv`` exist, then re-runs
    the headless audit (:func:`verify_run`) over every run the index lists -- a listed run that
    does NOT reproduce fails the gate (the package cannot stand on a record that does not
    re-derive). Returns ``(runs, runs_reproduced, problems)``.
    """
    problems: List[str] = []

    claims_csv = package_dir / "02_data" / "claims_all.csv"
    if not claims_csv.is_file():
        problems.append("traceability: 02_data/claims_all.csv is missing")

    runs = _run_index_runs(package_dir)
    runs_reproduced: Dict[str, bool] = {}
    if runs is None:
        problems.append("record green: 06_provenance/run_index.csv is missing")
        return [], runs_reproduced, problems

    for rid in runs:
        run_dir = workspace_dir / "runs" / rid
        if not (run_dir / "spec.json").is_file():
            problems.append(
                f"record green: run '{rid}' in run_index.csv has no runs/{rid}/spec.json"
            )
            runs_reproduced[rid] = False
            continue
        try:
            report = verify_run(run_dir)
        except (FileNotFoundError, ValueError) as exc:
            problems.append(
                f"record green: run '{rid}' could not be audited: {exc}"
            )
            runs_reproduced[rid] = False
            continue
        runs_reproduced[rid] = report.all_reproduced
        if not report.all_reproduced:
            problems.append(
                f"record green: run '{rid}' does not reproduce from its record "
                "(at least one claim DIVERGED or is UNRESOLVED)"
            )
    return runs, runs_reproduced, problems


# -- read-only loaders -------------------------------------------------------

def _load_spec(run_dir: Path) -> Spec:
    spec_path = run_dir / "spec.json"
    if not spec_path.exists():
        raise FileNotFoundError(f"no spec.json found in run dir: {run_dir}")
    return Spec.model_validate(json.loads(spec_path.read_text(encoding="utf-8")))


def _load_evidence(run_dir: Path) -> List[EvidenceItem]:
    """Load the recorded append-only Evidence log (read-only)."""
    evidence_dir = run_dir / "evidence"
    if not evidence_dir.is_dir():
        return []
    items: List[EvidenceItem] = []
    for path in sorted(evidence_dir.glob("*.json")):
        items.append(
            EvidenceItem.model_validate(json.loads(path.read_text(encoding="utf-8")))
        )
    return items


def _load_claims(run_dir: Path) -> Dict[str, Claim]:
    """Load recorded Claims keyed by their unique Claim ``id`` (read-only).

    Keyed by ``claim.id`` (not ``claim.answers``) because the two-claim model
    (B-replace) means a hypothesis can have BOTH an experiment claim ``claim-<hyp>`` and
    a novelty claim ``claim-novelty-<hyp>`` answering the SAME hypothesis id -- keying by
    ``answers`` would silently drop one. The audit routes each by id.
    """
    claims_dir = run_dir / "claims"
    if not claims_dir.is_dir():
        return {}
    claims: Dict[str, Claim] = {}
    for path in sorted(claims_dir.glob("*.json")):
        claim = Claim.model_validate(json.loads(path.read_text(encoding="utf-8")))
        claims[claim.id] = claim
    return claims


__all__ = [
    "REPRODUCED",
    "DIVERGED",
    "UNRESOLVED",
    "VerifyOutcome",
    "VerifyReport",
    "verify_run",
    "PackageVerifyReport",
    "verify_package",
]
