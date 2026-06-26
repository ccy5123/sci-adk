"""
ResearchCompiler -- the deterministic orchestrator (the research compiler core).

Drives a four-pane proposal through the parts that need NO LLM (zero cost):

    proposal text
        -> parse (ProposalParser)            -> Spec        (runs/<id>/spec.json)
        -> [experiment hook]                 -> Evidence    (runs/<id>/evidence/)
        -> ClaimUpdater + DecisionEngine     -> Claims      (runs/<id>/claims/)
        -> render_paper_latex                -> draft       (runs/<id>/paper/draft.tex)

LLM-dependent steps are NOT run autonomously here (design/tool-policy.md: the LLM
is Claude Code, and a per-call ``claude -p`` subprocess costs tokens). Instead,
``proof`` / ``qualitative`` hypotheses are surfaced as *agent checkpoints* -- the
in-session agent (already running, zero extra cost) supplies the verdicts and the
run is recompiled with an injected ``judge``. The compiler never spawns
``claude -p`` and never calls an API.

Experiment execution is a pluggable hook: ``compile(experiment=fn)`` where
``fn(spec, workspace_dir) -> [EvidenceItem]``. The kernel keeps only the
``ExperimentFn`` *type*; concrete experiment factories live in the capability
adapter (``sci_adk.adapter``), never here -- the kernel stays domain-free
(design/rigor-shell-architecture.md §2.4/§3.3, F4). A capability may also supply a
pre-built ``Spec`` via ``compile(spec=...)`` when the free-text parser cannot infer
the precise ``DecisionRule`` (e.g. a numeric threshold rule).

Reference: design/rigor-shell-architecture.md (kernel/adapter seam),
design/directory-structure.md (loop/), design/decision-engine.md.
"""

from __future__ import annotations

import csv
import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional, Sequence

from sci_adk.core.claim import Claim, ClaimStatus
from sci_adk.core.evidence import EvidenceItem, EvidenceKind
from sci_adk.core.parser import ProposalParser
from sci_adk.core.spec import DecisionRuleKind, Spec
from sci_adk.core.spec_science import ScienceFinding, audit_spec_science
from sci_adk.loop.claim_updater import ClaimUpdater, _NOVELTY_KINDS
from sci_adk.loop.judge import Judge
from sci_adk.loop.literature_triggers import (
    contested_checkpoint,
    contested_open,
    novelty_checkpoint,
    novelty_open,
    novelty_reason_from_decisions,
)
from sci_adk.loop.prior_work import prior_work_checkpoint
from sci_adk.loop.verdict import (
    CheckpointModel,
    ContestedCheckpoint,
    NoveltyCheckpoint,
    PriorWorkCheckpoint,
)
from sci_adk.render.figures import (
    AnyFigure,
    FigureConsistencyReport,
    ImageFigureSpec,
    check_figure_consistency,
    figure_labels,
    image_figure_filename,
    order_figures_by_reference,
)
from sci_adk.render.paper import render_paper_latex
from sci_adk.render.prose import PaperProse, SIProse
from sci_adk.render.reproduction import (
    ReproListing,
    listing_inlinable,
    render_reproduce_driver,
)
from sci_adk.render.si import render_si_latex

# An experiment hook turns a Spec into Evidence (e.g. by running code in Docker).
ExperimentFn = Callable[[Spec, Path], Sequence[EvidenceItem]]

# Rule kinds the engine cannot reduce to a formula -> need an agent/judge.
_NON_NUMERIC = {DecisionRuleKind.PROOF, DecisionRuleKind.QUALITATIVE}


@dataclass(frozen=True)
class Checkpoint:
    """A hypothesis awaiting an in-session agent verdict (no autonomous LLM).

    ``spec_version`` is carried so the typed ``checkpoints/<hyp-id>.json`` is
    self-describing for replay (design/rigor-shell-architecture.md §4.3).
    """

    hypothesis_id: str
    kind: str             # "proof" | "qualitative"
    expression: str       # the rule's prose criterion
    finding: str = ""     # evidence finding(s) the agent should judge, if any
    spec_version: int = 1  # the Spec version this checkpoint was raised against

    def to_model(self) -> CheckpointModel:
        """The typed contract behind ``checkpoints/<hyp-id>.json`` (F1)."""
        return CheckpointModel(
            hypothesis_id=self.hypothesis_id,
            kind=self.kind,
            expression=self.expression,
            finding=self.finding,
            spec_version=self.spec_version,
        )


@dataclass
class CompileResult:
    """The output of one compilation."""

    spec: Spec
    evidence: List[EvidenceItem]
    claims: List[Claim]
    checkpoints: List[Checkpoint]
    run_dir: Path
    paper_path: Path
    si_path: Optional[Path] = None
    prior_work_checkpoint: Optional[PriorWorkCheckpoint] = None
    contested_checkpoints: List[ContestedCheckpoint] = field(default_factory=list)
    novelty_checkpoints: List[NoveltyCheckpoint] = field(default_factory=list)
    figure_consistency: Optional[FigureConsistencyReport] = None
    science_findings: List[ScienceFinding] = field(default_factory=list)

    @property
    def needs_agent(self) -> bool:
        """True when proof/qualitative checkpoints await an in-session verdict."""
        return bool(self.checkpoints)


class ResearchCompiler:
    """
    Compile a proposal into a Spec + Evidence + Claims + a paper draft.

    The numeric path is fully autonomous and free. proof/qualitative are surfaced
    as checkpoints unless a ``judge`` is injected (the in-session agent's verdicts
    on a recompile) -- never an autonomous claude -p / API call.
    """

    def __init__(
        self,
        workspace_dir: Optional[Path] = None,
        judge: Optional[Judge] = None,
        strict_science: bool = False,
    ) -> None:
        self.workspace_dir = Path(workspace_dir) if workspace_dir else Path.cwd()
        self.judge = judge
        # strict_science: forwarded to the ClaimUpdater so the science-guard verdict-gate
        # HALTS (design/science-guards.md) are enforced. Default False -- the lenient
        # PRIMITIVE contract (a library caller of compile()/stage_derive_claim is not
        # blocked; the weakness is still surfaced at the spec gate + by verify). The CLI
        # research entrypoints (`sci-adk run` / `derive-claim`, the sci verb) construct the
        # compiler with strict_science=True so a real run refuses a weak SUPPORTED.
        self.strict_science = strict_science

    def compile(
        self,
        proposal_text: str,
        *,
        spec_id: Optional[str] = None,
        spec: Optional[Spec] = None,
        experiment: Optional[ExperimentFn] = None,
        prose: Optional[PaperProse] = None,
        si_prose: Optional[SIProse] = None,
        figures: Optional[Sequence[AnyFigure]] = None,
        si_figures: Optional[Sequence[AnyFigure]] = None,
    ) -> CompileResult:
        """
        Compile a proposal end to end into ``runs/<spec.id>/``.

        Args:
            proposal_text: the four-pane proposal. Ignored when ``spec`` is given.
            spec_id: optional explicit Spec id (else derived by the parser). Ignored
                when ``spec`` is given.
            spec: an optional pre-built ``Spec`` supplied by a capability adapter.
                When present it is used verbatim (the heuristic parser is bypassed),
                letting a capability carry a precise ``DecisionRule`` the free-text
                parser cannot infer -- e.g. a numeric threshold rule. The kernel
                stays domain-free: it accepts a frozen ``Spec``, never the domain.
            experiment: optional ``fn(spec, workspace_dir) -> [EvidenceItem]``
                that produces Evidence (e.g. a Docker run). When absent, the
                compile still emits the Spec + a proposal-only draft + any
                proof/qualitative checkpoints.
            prose: optional agent-authored narrative (abstract/introduction/
                discussion) injected into BOTH the Markdown and LaTeX drafts. Never
                LLM-generated -- it is input the in-session agent (or a --prose file)
                supplies, the same spirit as ``pending``.
            si_prose: optional agent-authored narrative wrapping the Supporting
                Information record dump -- ``overview`` before the Evidence record,
                ``notes`` after Record integrity (design/paper-figures-and-si.md D3,
                Phase 4). Threaded into ``render_si_latex``; the no-authoring record dump
                is the spine and is never replaced. Never LLM-generated -- input, the same
                spirit as ``prose``. Absent -> si.tex is byte-identical to the no-prose
                dump.
            figures: optional agent-authored figure list -- native (pgfplots) or image
                (``\\includegraphics``) specs (design/paper-figures-and-si.md, Phase
                1/4). Threaded into the LaTeX renderers (native y pulled from this run's
                Evidence; image specs reference co-located ``figures/<id><ext>``). Never
                LLM-generated -- input, the same spirit as ``prose``. For each IMAGE
                spec the compiler co-locates its source file into ``paper/figures/`` so
                the ``.tex`` reference resolves on an Overleaf folder-upload (a missing
                source fails loud, record fidelity). After rendering, a NON-BLOCKING
                ``check_figure_consistency`` over the rendered body is surfaced in
                ``CompileResult.figure_consistency`` (a report, not a gate; the hard
                verify-gate is Phase 3). These are the MAIN figures -- they appear ONLY in
                the paper's Results (the SI carries only ``si_figures``). Absent -> no
                figures.
            si_figures: optional SUPPLEMENTARY figures rendered ONLY in the SI (default
                none). The main ``figures`` are never re-rendered in the SI, so a main
                figure is not duplicated across draft.tex + si.tex (design feedback 5.2).

        Returns:
            A ``CompileResult`` (inspect ``needs_agent`` / ``checkpoints``).
        """
        # @MX:ANCHOR: [AUTO] the end-to-end compile is now literally the §4.6 stage chain
        #   (init_spec -> execute -> derive_claim -> render). `sci-adk run` and the 6
        #   standalone CLI verbs both run THESE stage functions, so there is one source of
        #   truth for each stage and `run` == the verb chain by construction.
        # @MX:REASON: [AUTO] every caller -- CLI run/verbs, checkpoint_loop, the adapter
        #   registry tests, and the byte-identity regression test -- depends on this chain
        #   producing exactly what the per-verb path produces. Diverging a stage from what
        #   the chain runs would silently desync `run` from the per-verb path (the
        #   decomposition contract) and break byte-identity.
        spec = self.stage_init_spec(
            spec=spec, proposal_text=proposal_text, spec_id=spec_id
        )

        # `run` threads the experiment's evidence in memory, but `stage_execute` returns it
        # in the CANONICAL (sorted-by-filename) order -- the SAME order the standalone
        # verbs get when they reload from disk. So the chain and the verb path render
        # Evidence in one identical order (run == verb chain), proven by the multi-evidence
        # byte-identity regression test. NOTE: on multi-evidence runs this canonical order
        # may differ from the pre-decomposition monolith's production order; that monolith
        # order was never canonical (verify/digest/F5-replay already sorted), so unifying on
        # the sorted order is the minimal-divergence fix.
        evidence = self.stage_execute(spec, experiment=experiment)

        claims, checkpoints, contested_checkpoints, novelty_checkpoints = (
            self.stage_derive_claim(spec, evidence=evidence)
        )

        paper_path, si_path, figure_consistency = self.stage_render(
            spec,
            evidence=evidence,
            claims=claims,
            checkpoints=checkpoints,
            prose=prose,
            si_prose=si_prose,
            figures=figures,
            si_figures=si_figures,
        )

        return CompileResult(
            spec=spec,
            evidence=evidence,
            claims=claims,
            checkpoints=checkpoints,
            run_dir=self.workspace_dir / "runs" / spec.id,
            paper_path=paper_path,
            si_path=si_path,
            prior_work_checkpoint=prior_work_checkpoint(spec),
            contested_checkpoints=contested_checkpoints,
            novelty_checkpoints=novelty_checkpoints,
            figure_consistency=figure_consistency,
            science_findings=audit_spec_science(spec),
        )

    # -- stage functions (design/sci-adk-as-moai.md §4.6) -------------------
    #
    # Each stage operates on the run directory, reads its prior state from disk when
    # not handed an in-memory value, performs its step, and persists its output. The
    # chained ``compile`` above threads in-memory values between stages (so ``run``
    # is byte-identical to the pre-decomposition monolith); the standalone CLI verbs
    # call ONE stage each and rely on the disk round-trip. The two paths run the SAME
    # stage code, so there is no second implementation to drift.

    def stage_init_spec(
        self,
        *,
        spec: Optional[Spec] = None,
        proposal_text: str = "",
        spec_id: Optional[str] = None,
    ) -> Spec:
        """Author/accept + freeze a Spec, then persist ``spec.json`` + the prior-work
        checkpoint (the ``init-spec`` verb's stage).

        When ``spec`` is supplied it is used verbatim (a capability adapter's pre-built
        Spec, bypassing the heuristic parser); otherwise the four-pane ``proposal_text``
        is parsed. The frozen Spec is written to ``runs/<spec.id>/spec.json`` and the
        Spec-time prior-work reminder to ``checkpoints/prior_work.json`` (a recording-type
        reminder, not a judgment -- design/literature-acquisition.md).
        """
        spec = spec if spec is not None else ProposalParser().parse(
            proposal_text, spec_id=spec_id
        )
        run_dir = self.workspace_dir / "runs" / spec.id
        run_dir.mkdir(parents=True, exist_ok=True)
        self._save_spec(spec, run_dir)

        # Spec-time prior-work trigger (design/literature-acquisition.md): emit a
        # recording-type reminder so prior art is not forgotten. It is NOT a
        # judgment (no verdict trail, not hypothesis-bound); it stays open until a
        # prior-work decision (searched -> LITERATURE / skipped -> PRIOR_WORK_DECISION)
        # is recorded in the single Evidence log.
        self._save_prior_work_checkpoint(prior_work_checkpoint(spec), run_dir)

        # Spec-gate science audit (design/science-guards.md): ALWAYS on, NEVER halts. Persist
        # the structural findings (G1/G2/G4/G5 + a G3 reminder) so a weak Spec is never
        # SILENTLY accepted -- the author resolves each by a Spec amendment, exactly like the
        # prior-work / novelty / contested reminders. The verdict-gate HALTS enforce the same
        # concerns at SUPPORTED-stamp time under strict_science.
        self._save_science_findings(audit_spec_science(spec), run_dir)
        return spec

    def stage_execute(
        self,
        spec: Spec,
        *,
        experiment: Optional[ExperimentFn] = None,
        force: bool = False,
    ) -> List[EvidenceItem]:
        """Execute the Spec's experiment hook into Evidence (the ``execute`` verb's stage).

        Honors the F5 reuse contract (design/rigor-shell-architecture.md §5, the same
        rule ``run_checkpoint_loop`` uses): when Evidence already exists on disk for this
        run and ``force`` is False, the recorded Evidence is REPLAYED rather than
        re-executing the experiment -- so a re-run is idempotent and the append-only log
        is not duplicated (E1). When no Evidence exists yet, the supplied ``experiment``
        is run (the t1 experiment self-persists each item; capabilities that do not
        self-persist still get a replayable record via :meth:`stage_append_evidence`'s
        writer in the verb path). An absent experiment with no recorded Evidence yields
        an empty list (the proposal-only path).

        CANONICAL ORDER (the byte-identity fix): the returned list is ALWAYS in the
        canonical on-disk order -- ``sorted(evidence_dir.glob("*.json"))`` -- regardless of
        the experiment's production order. This is the SAME order ``_load_existing_evidence``
        (F5 replay), ``verify``, ``record_digest``, and ``run_checkpoint_loop`` iteration
        2+ already use, so adopting it for the FIRST pass too means ``compile``/``run``
        (which thread this list) and the standalone verbs (which reload from disk) render
        Evidence in ONE identical order by construction. Production order is NOT canonical:
        sorting by ``created_at`` would break on equal/sub-second-tied timestamps (e.g. a
        single experiment call), so the deterministic filename sort is the robust invariant.

        The chained ``compile`` passes the experiment directly (first run -> fresh
        Evidence); the standalone ``execute`` verb relies on the SAME F5 reuse so a
        second invocation over a populated run dir replays instead of re-generating.
        """
        # @MX:NOTE: [AUTO] F5 reuse is silent: when evidence/ is populated and force is
        #   False this REPLAYS the recorded Evidence and never calls `experiment`. This is
        #   why `run` over a pre-seeded run dir reproduces a prior run byte-for-byte
        #   (shared with run_checkpoint_loop's reuse), and why a bare `execute` with no
        #   capability still works when Evidence exists.
        # @MX:ANCHOR: [AUTO] this stage is the SINGLE point that defines the canonical
        #   Evidence ORDER for the whole pipeline: it always returns the sorted-by-filename
        #   disk order, so `run`/`compile` and the standalone verbs render Evidence in the
        #   identical order (no production-vs-sorted divergence).
        # @MX:REASON: [AUTO] compile(), run_checkpoint_loop iteration 1, and the execute
        #   verb all flow through here; the renderers (render_paper_latex / render_si_latex)
        #   iterate the supplied order. If this returned production order on the first pass
        #   but the verbs/verify/replay read sorted order, draft.tex + si.tex would reorder
        #   between `run` and the verb chain on multi-evidence runs -- the exact regression
        #   this fix closes. The order MUST match `_load_existing_evidence`'s sorted glob.
        from sci_adk.loop.checkpoint_loop import (
            _load_existing_evidence,
            _persist_evidence,
        )

        run_dir = self.workspace_dir / "runs" / spec.id
        if not force:
            existing = _load_existing_evidence(run_dir)
            if existing:
                return existing
        if experiment is None:
            return []
        produced = experiment(spec, self.workspace_dir)
        evidence = list(produced) if produced else []
        # Persist so a downstream verb (derive-claim/render) can reload it. Idempotent:
        # each item is keyed by its stable id (a self-persisting experiment overwrites
        # byte-identical content; a non-self-persisting one gets its record here).
        _persist_evidence(run_dir, evidence)
        # Re-read in CANONICAL (sorted) order so the in-memory return == the disk order the
        # verbs/verify/replay see -- this is what makes `run` == the verb chain on
        # multi-evidence runs. A no-op for the common single-item run.
        return _load_existing_evidence(run_dir)

    def stage_append_evidence(
        self, spec: Spec, item: EvidenceItem
    ) -> EvidenceItem:
        """Append one typed ``EvidenceItem`` to the run's append-only log (the
        ``append-evidence`` verb's stage).

        The single-item complement to :meth:`stage_execute`: a worker that produced
        Evidence out-of-band (its own tool, a manual record) appends it here. The item
        is written to ``runs/<spec.id>/evidence/<id>.json`` via the shared persister
        (E1 append-only; keyed by the stable ``item.id``). The chained ``compile`` does
        not call this -- its experiment IS the append -- so it never double-writes.
        """
        from sci_adk.loop.checkpoint_loop import _persist_evidence

        run_dir = self.workspace_dir / "runs" / spec.id
        _persist_evidence(run_dir, [item])
        return item

    def stage_derive_claim(
        self,
        spec: Spec,
        *,
        evidence: Optional[Sequence[EvidenceItem]] = None,
    ) -> tuple[
        List[Claim],
        List["Checkpoint"],
        List[ContestedCheckpoint],
        List[NoveltyCheckpoint],
    ]:
        """Apply each hypothesis's frozen DecisionRule to the Evidence -> Claims, and
        collect the recording-type checkpoints (the ``derive-claim`` verb's stage).

        Loads the Evidence from disk when ``evidence`` is not supplied (the verb path);
        the chained ``compile`` passes the in-memory list (byte-identical to the
        monolith). Runs the ``ClaimUpdater`` (which persists ``claims/``), then collects:
          - the proof/qualitative judge checkpoints (persisted to ``checkpoints/``);
          - the CONTESTED recording reminders (the Medium discovery trigger);
          - the novelty recording reminders (the High discovery trigger, 2-kind).

        The contested/novelty reasons are derived from the SAME ``evidence`` the claims
        were derived from (not a second disk read) so the surfaced messages and the
        persisted claim statuses agree in this single pass.
        """
        evidence_list = (
            list(evidence) if evidence is not None
            else self._load_evidence(spec)
        )

        claims: List[Claim] = []
        if evidence_list:
            claims = ClaimUpdater(
                spec, self.workspace_dir, judge=self.judge,
                strict_science=self.strict_science,
            ).update_claims_from_evidence(evidence_list)

        checkpoints = self._collect_checkpoints(spec, evidence_list)

        # Contested surfacing (the Medium discovery trigger,
        # design/literature-acquisition.md): for every hypothesis whose freshly
        # persisted Claim is CONTESTED and has no CONTESTED_RECORD yet, surface a
        # recording-type contested checkpoint. This is a reminder, NOT a gate -- nothing
        # halts. The append-only ``created_at`` already supplies the anti-post-hoc
        # timestamp; recording it makes the post-conflict literature decision explicit.
        contested_checkpoints = self._collect_contested_checkpoints(spec, claims)

        # Novelty surfacing (the High discovery trigger, B-replace): for every
        # novelty=True hypothesis whose ``claim-novelty-<hyp>`` is still PROPOSED, surface
        # a reason-tailored NON-HALT NoveltyCheckpoint. The compile PROCEEDS normally --
        # this is a recording reminder, not a gate. ``novelty_open`` keys on the
        # novelty claim ClaimUpdater just persisted, so a re-compile after a found_nothing
        # decision (claim SUPPORTED) surfaces nothing. The reason is derived from the SAME
        # ``evidence`` the claim was derived from (NOT a second disk read) so the message
        # and the claim status agree even in this single pass.
        novelty_checkpoints = self._collect_novelty_checkpoints(
            spec, claims, evidence_list
        )

        if checkpoints:
            self._save_checkpoints(checkpoints, run_dir=self.workspace_dir / "runs" / spec.id)

        return claims, checkpoints, contested_checkpoints, novelty_checkpoints

    def stage_render(
        self,
        spec: Spec,
        *,
        evidence: Optional[Sequence[EvidenceItem]] = None,
        claims: Optional[Sequence[Claim]] = None,
        checkpoints: Optional[Sequence["Checkpoint"]] = None,
        prose: Optional[PaperProse] = None,
        si_prose: Optional[SIProse] = None,
        figures: Optional[Sequence[AnyFigure]] = None,
        si_figures: Optional[Sequence[AnyFigure]] = None,
    ) -> tuple[Path, Optional[Path], Optional[FigureConsistencyReport]]:
        """Render the ``paper/`` artifacts -- ``draft.tex`` + ``si.tex`` + figures + bib
        (the ``render`` verb's stage).

        The MAIN figures (``figures``) appear ONLY in the paper's Results; the SI carries
        only ``si_figures`` (supplementary, default none) -- so a main figure is never
        duplicated across the two documents (design feedback 5.2). The co-located
        ``references.bib`` is wired into BOTH documents (the SI's ``\\citep`` resolved too).

        Loads Evidence, Claims, and the judge checkpoints from disk when not supplied
        (the verb path); the chained ``compile`` passes the in-memory values
        (byte-identical to the monolith). The render itself is pure (data in, string
        out); this stage is the composition root that locates the citations + bib and
        co-locates figure/bib sources into ``paper/`` for Overleaf self-containment.

        Returns ``(paper_path, si_path, figure_consistency)``.
        """
        evidence_list = (
            list(evidence) if evidence is not None
            else self._load_evidence(spec)
        )
        claims_list = (
            list(claims) if claims is not None
            else self._load_claims(spec)
        )
        checkpoints_list = (
            list(checkpoints) if checkpoints is not None
            else self._load_checkpoints(spec, evidence_list)
        )

        run_dir = self.workspace_dir / "runs" / spec.id

        # Citations + bibliography are gathered for the run (renderers stay pure --
        # data in, string out; the compiler is the composition root that locates them).
        pending_dicts = [c.__dict__ for c in checkpoints_list]
        cited_dois = self._gather_cited_dois(evidence_list, run_dir)

        paper_dir = run_dir / "paper"
        paper_dir.mkdir(parents=True, exist_ok=True)

        # Co-locate references.bib next to draft.tex so the paper/ folder is
        # self-contained on Overleaf (upload-as-is resolves \bibliography{references}).
        # The compiler does the copy (the renderer stays pure); it then passes the
        # CO-LOCATED path, whose stem is "references", to the renderer.
        bib_path = self._colocate_bib(run_dir, paper_dir)

        figures = list(figures or [])
        si_figures = list(si_figures or [])

        # The .tex is THE paper artifact (Overleaf default pdflatex). Deterministic and
        # offline -- no LLM, no network (render_paper_latex is pure). The Markdown
        # render_paper remains a library function but is no longer auto-emitted. It is
        # rendered FIRST (before co-location) because its body fixes the canonical
        # body-reference figure numbering (Figure 1 = first-\ref'd) that the co-located
        # fig<N> filenames AND the SI must agree with.
        paper_tex = render_paper_latex(
            spec, claims_list, evidence_list,
            pending=pending_dicts,
            prose=prose,
            cited_dois=cited_dois,
            bib_path=bib_path,
            figures=figures,
        )
        paper_path = paper_dir / "draft.tex"
        paper_path.write_text(paper_tex, encoding="utf-8")

        # Co-locate each IMAGE figure's source into paper/figures/fig<N><ext> (the
        # renderer only emits that reference; the compiler -- the sole filesystem toucher
        # -- lands the bytes), so the paper/ folder is self-contained on an Overleaf
        # upload. The numbering N is computed ONCE from the rendered draft body (the same
        # pure order_figures_by_reference the renderer used; refs only precede the Figures
        # section, so scanning the full draft yields the identical order), so the
        # \includegraphics path and the co-located filename agree exactly. A missing
        # source fails loud here (record fidelity). Native specs carry no file.
        self._colocate_figures(figures, paper_dir, paper_tex)

        # Supporting Information (design/paper-figures-and-si.md Phase 2 / D3): a
        # STANDALONE si.tex = the deterministic record dump (every Evidence item, the
        # numeric data tables, ALL figures, the verdicts + frozen decision rules). It
        # uploads alongside draft.tex as a second compilable document in paper/.
        #
        # digest=None on purpose: at COMPILE time the evidence may not yet be persisted to
        # disk (the loop persists AFTER compile), so record_digest(run_dir) here would
        # digest an INCOMPLETE run dir. So Phase 2 does NOT embed the digest -- the SI's
        # integrity section points to `sci-adk verify` (which recomputes the digest over
        # the persisted run). Embedding the real digest at render time is a later
        # refinement. (Cross-DOCUMENT main<->SI \ref -- e.g. "Fig. S2" in the main paper
        # resolving into the SI -- is deferred to Phase 3: separate compiles would need
        # the `xr` package + a compile-order dependency; the SI is INTERNALLY consistent
        # here via figure_labels' unique-id enforcement.)
        # paper_body=paper_tex: the SI shares the SAME global fig<N> body-reference
        # numbering as the main draft (Figure N here == Figure N there), so si.tex
        # references the same paper/figures/fig<N> files the compiler co-located above --
        # one shared file set for both standalone documents.
        # F3 reproduction bundle (design/paper-publishing-requirements.md §3): resolve each
        # Evidence item's provenance.code_ref -> (co-located script | bare-ref pointer),
        # then (a) inline the listings in the SI's "Reproduction code" section, (b)
        # co-locate the resolvable scripts into paper/code/, and (c) write paper/reproduce.py.
        # The compiler -- the SOLE filesystem toucher -- does the resolution + fs; the SI
        # renderer stays pure (it receives the resolved listings). When NO Evidence item
        # carries a code_ref, repro_listings is empty -> no section, no paper/code/, no
        # reproduce.py (the run's paper/ is byte-identical to today; the F3 regression
        # invariant). Resolution is fail-open: a bare commit ref is a POINTER, never an error.
        repro_listings = self._resolve_repro_listings(evidence_list, run_dir)

        si_tex = render_si_latex(
            spec, claims_list, evidence_list, figures=si_figures, digest=None,
            prose=si_prose, paper_body=None, bib_path=bib_path,
            repro_listings=repro_listings,
        )
        si_path = paper_dir / "si.tex"
        si_path.write_text(si_tex, encoding="utf-8")

        # Land the runnable bundle (paper/code/ + paper/reproduce.py) ONLY when at least
        # one code_ref resolved to a co-located script. A pointer-only set (every code_ref
        # a bare commit, as in an all-pointer run) still documents the commits in reproduce.py, but
        # only when there is something to drive: an entirely code_ref-free run writes
        # nothing (byte-identical paper/). See _emit_reproduction_bundle.
        self._emit_reproduction_bundle(repro_listings, paper_dir, spec.id)

        # Prose<->figure ref consistency (design/paper-figures-and-si.md D4): scan the
        # RENDERED body for \ref{fig:...}/\label integrity. NON-BLOCKING -- surfaced in
        # the result (a warning channel, like the contested/novelty checkpoints), never
        # a hard fail (the verify-style gate is Phase 3). figure_labels enforces unique
        # ids; rendering above would already have raised on a missing evidence id.
        figure_consistency = check_figure_consistency(
            figure_labels(figures), paper_tex
        )
        return paper_path, si_path, figure_consistency

    # -- disk loaders (the verb path reads its inputs from the run dir) -----

    def _load_evidence(self, spec: Spec) -> List[EvidenceItem]:
        """Load the recorded append-only Evidence log for ``spec`` (read-only).

        Reuses the SAME loader the F5 reuse path and the headless ``verify`` use
        (``checkpoint_loop._load_existing_evidence`` -> ``sorted(glob("*.json"))``), so a
        standalone ``derive-claim`` / ``render`` verb sees Evidence in exactly the order
        the loop and the audit do. Empty when no ``evidence/`` exists yet.
        """
        from sci_adk.loop.checkpoint_loop import _load_existing_evidence

        return _load_existing_evidence(self.workspace_dir / "runs" / spec.id)

    def _load_claims(self, spec: Spec) -> List[Claim]:
        """Load the recorded Claims for ``spec`` in the SAME order ``ClaimUpdater``
        produced them (experiment claims per hypothesis, then per-{hypothesis, kind}
        novelty claims).

        ``ClaimUpdater.update_claims_from_evidence`` returns claims hypothesis-by-
        hypothesis (``claim-<hyp>``) followed by the per-kind novelty claims
        (``claim-novelty-{kind}-<hyp>``); a naive ``sorted(glob)`` would reorder them and
        could change the rendered Claims ordering. Reconstructing the updater's order here
        keeps the standalone ``render`` verb byte-identical to the chained ``compile``.
        Only claims that exist on disk are returned (a hypothesis with no counted Evidence
        has no ``claim-<hyp>``; a non-novelty hypothesis has no novelty claim).
        """
        claims_dir = self.workspace_dir / "runs" / spec.id / "claims"
        if not claims_dir.is_dir():
            return []

        def _load(claim_id: str) -> Optional[Claim]:
            path = claims_dir / f"{claim_id}.json"
            if not path.exists():
                return None
            return Claim.model_validate(json.loads(path.read_text(encoding="utf-8")))

        ordered: List[Claim] = []
        for h in spec.hypotheses:
            claim = _load(f"claim-{h.id}")
            if claim is not None:
                ordered.append(claim)
        for h in spec.hypotheses:
            for kind in _NOVELTY_KINDS:
                claim = _load(f"claim-novelty-{kind}-{h.id}")
                if claim is not None:
                    ordered.append(claim)
        return ordered

    def _load_checkpoints(
        self, spec: Spec, evidence: Sequence[EvidenceItem]
    ) -> List["Checkpoint"]:
        """Reconstruct the proof/qualitative judge checkpoints for ``render``.

        Checkpoints are deterministic from the Spec + Evidence (the proof/qualitative
        hypotheses with any bearing finding), so the ``render`` verb regenerates them via
        the SAME pure :meth:`_collect_checkpoints` the chain uses rather than re-reading
        ``checkpoints/`` -- one source of truth, and it does not depend on the judge
        checkpoint files having been written. ``pending`` in the rendered paper is built
        from these, so the regenerated list matches the chain's.
        """
        return self._collect_checkpoints(spec, evidence)

    # -- helpers -----------------------------------------------------------

    @staticmethod
    def _gather_cited_dois(
        evidence: Sequence[EvidenceItem], run_dir: Path
    ) -> List[str]:
        """Collect the DOIs to cite for this run, de-duplicated, first-seen order.

        Two sources (a cited DOI is cited regardless of whether its PDF downloaded):
          (a) ``LITERATURE`` EvidenceItems -- their ``result.finding`` is the JSON
              summary the acquirer writes (``acquired[].doi`` + ``failed[].doi``);
          (b) the run's ``artifacts/literature/manifest.csv`` (the literature-manifest shape,
              where literature was acquired ad-hoc with no LITERATURE EvidenceItem).

        Pure parsing of recorded artifacts -- no acquisition, no network.
        """
        seen: List[str] = []

        def _add(doi: Optional[str]) -> None:
            d = (doi or "").strip()
            if d and d not in seen:
                seen.append(d)

        # (a) LITERATURE evidence findings.
        for ev in evidence:
            if ev.kind != EvidenceKind.LITERATURE:
                continue
            finding = ev.result.finding
            if not finding:
                continue
            try:
                summary = json.loads(finding)
            except (json.JSONDecodeError, TypeError):
                continue
            if not isinstance(summary, dict):
                continue
            for bucket in ("acquired", "failed"):
                for entry in summary.get(bucket, []) or []:
                    if isinstance(entry, dict):
                        _add(entry.get("doi"))

        # (b) manifest.csv on disk.
        manifest = run_dir / "artifacts" / "literature" / "manifest.csv"
        if manifest.exists():
            try:
                with manifest.open(encoding="utf-8", newline="") as fh:
                    for row in csv.DictReader(fh):
                        _add(row.get("doi"))
            except (OSError, csv.Error):
                pass

        return seen

    @staticmethod
    def _locate_bib_path(run_dir: Path) -> Optional[str]:
        """Return the run's ``artifacts/literature/references.bib`` path when present.

        The renderer wires an EXISTING ``.bib`` (it never generates one); this just
        locates it. ``None`` when absent -> the renderer emits no ``\\bibliography``.
        """
        bib = run_dir / "artifacts" / "literature" / "references.bib"
        return str(bib) if bib.exists() else None

    @classmethod
    def _colocate_bib(cls, run_dir: Path, paper_dir: Path) -> Optional[str]:
        """Copy the run's ``references.bib`` next to ``draft.tex`` and return its path.

        Overleaf self-containment: when ``_locate_bib_path`` finds the run's
        ``artifacts/literature/references.bib``, copy it verbatim to
        ``paper/references.bib`` so uploading the ``paper/`` folder as-is resolves
        ``\\bibliography{references}``. The returned path's stem is ``references``, so
        the (pure) renderer emits exactly that ``\\bibliography`` key. ``None`` when no
        source ``.bib`` exists -> the renderer emits no ``\\bibliography``. No BibTeX is
        generated -- this is a faithful copy of an existing file.
        """
        src = cls._locate_bib_path(run_dir)
        if src is None:
            return None
        dest = paper_dir / "references.bib"
        shutil.copyfile(src, dest)
        return str(dest)

    def _colocate_figures(
        self, figures: Sequence[AnyFigure], paper_dir: Path, paper_body: str
    ) -> None:
        """Copy each IMAGE figure's source file into ``paper/figures/fig<N><ext>``.

        Overleaf self-containment (mirrors :meth:`_colocate_bib`): the pure
        :func:`render_image_figure` emits ``\\includegraphics{figures/fig<N><ext>}`` but
        never touches the filesystem; the compiler -- the sole filesystem toucher --
        lands the actual bytes here so uploading the ``paper/`` folder as-is resolves
        the reference.

        The destination filename is the GENERIC, domain-free figure NUMBER ``fig<N>``
        (never the agent's id) with the SOURCE extension. ``N`` is the SHARED
        body-reference numbering: it is computed from ``paper_body`` (the just-rendered
        ``draft.tex``) via the SAME pure :func:`order_figures_by_reference` the renderer
        used, so the co-located filename and the renderer's ``\\includegraphics`` path
        agree EXACTLY (the numbering is computed once per consumer from the same body, not
        duplicated divergently). :func:`image_figure_filename` is the single name-builder
        both this method and the renderer's filename share. A relative ``spec.image`` is
        resolved against ``self.workspace_dir``. Native figures carry no file and are
        skipped (they still occupy a body-order position, just no renamed file).

        Raises:
            ValueError: if an image figure's source file does not exist -- fail-loud
                record fidelity (naming the figure id and the missing path), so a
                broken paper/ is never silently produced.
        """
        if not any(isinstance(f, ImageFigureSpec) for f in figures):
            return
        figures_dir = paper_dir / "figures"
        figures_dir.mkdir(parents=True, exist_ok=True)
        # The SAME body-reference numbering the renderer assigned (refs precede the
        # Figures section, so scanning the full draft gives the identical order).
        for number, fig in order_figures_by_reference(figures, paper_body):
            if not isinstance(fig, ImageFigureSpec):
                continue  # native: no file, keeps its body-order number only
            src = Path(fig.image)
            if not src.is_absolute():
                src = self.workspace_dir / src
            if not src.is_file():
                raise ValueError(
                    f"figure '{fig.id}': image source not found: {src} "
                    f"(an image figure must reference an existing file -- record "
                    f"fidelity; the paper/ folder must be self-contained)"
                )
            dest = figures_dir / image_figure_filename(fig, number)
            shutil.copyfile(src, dest)

    def _resolve_repro_listings(
        self, evidence: Sequence[EvidenceItem], run_dir: Path
    ) -> List[ReproListing]:
        """Resolve each Evidence item's ``provenance.code_ref`` for the F3 bundle (§3).

        For each item carrying a ``code_ref``, decide -- DETERMINISTICALLY, no LLM -- one
        of two outcomes (design/paper-publishing-requirements.md §3, OF-4 fail-open):

          - ``script``  -- the ``code_ref``, interpreted as a path RELATIVE TO the run dir
            (then the workspace), points at an EXISTING READABLE FILE whose body can be
            safely inlined (:func:`listing_inlinable`). The body is read here (the compiler
            is the sole filesystem toucher; the renderers stay pure) and the
            ``paper/code/`` basename is recorded; the script is co-located + driven by
            ``reproduce.py``.
          - ``pointer`` -- everything else: a bare commit/ref (e.g. a 40-hex git hash, the
            all-pointer shape), a missing path, an unreadable file, OR a body that cannot be
            safely inlined. Recorded as a POINTER -- NEVER an error (fail-open), honest
            about holding only the reference.

        Items with no ``code_ref`` contribute nothing -> an entirely code_ref-free run
        yields ``[]`` (the F3 byte-identical regression invariant). First-seen Evidence
        order is preserved (deterministic). Co-located filenames are de-collided so two
        scripts that share a basename land at distinct ``paper/code/`` names.
        """
        out: List[ReproListing] = []
        used_names: set[str] = set()
        for ev in evidence:
            code_ref = (ev.provenance.code_ref or "").strip()
            if not code_ref:
                continue
            resolved = self._resolve_code_ref_path(code_ref, run_dir)
            if resolved is None:
                out.append(
                    ReproListing(
                        evidence_id=ev.id, code_ref=code_ref, kind="pointer"
                    )
                )
                continue
            try:
                body = resolved.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                # Unreadable / non-text: honest pointer, never a fail-loud (fail-open).
                out.append(
                    ReproListing(
                        evidence_id=ev.id, code_ref=code_ref, kind="pointer"
                    )
                )
                continue
            if not listing_inlinable(body):
                # Body carries the lstlisting closing delimiter -> cannot inline safely;
                # record a pointer so the SI is never a broken document (honest).
                out.append(
                    ReproListing(
                        evidence_id=ev.id, code_ref=code_ref, kind="pointer"
                    )
                )
                continue
            filename = self._dedupe_code_filename(resolved.name, used_names)
            out.append(
                ReproListing(
                    evidence_id=ev.id,
                    code_ref=code_ref,
                    kind="script",
                    text=body,
                    filename=filename,
                )
            )
        return out

    def _resolve_code_ref_path(
        self, code_ref: str, run_dir: Path
    ) -> Optional[Path]:
        """Resolve a ``code_ref`` to an existing readable FILE, or ``None`` (a pointer).

        Interpret ``code_ref`` as a path relative to the run dir first (the natural home of
        co-located generating code), then the workspace; an absolute path is honored as-is.
        Returns the :class:`Path` iff it points at an existing regular file. A bare commit
        hash (no such path) -> ``None`` -> a POINTER. Pure + deterministic; read-only.
        """
        candidate = Path(code_ref)
        roots: List[Path]
        if candidate.is_absolute():
            roots = [candidate]
        else:
            roots = [run_dir / candidate, self.workspace_dir / candidate]
        for path in roots:
            if path.is_file():
                return path
        return None

    @staticmethod
    def _dedupe_code_filename(name: str, used: set[str]) -> str:
        """A unique ``paper/code/`` basename for ``name`` (deterministic de-collision).

        Two resolvable scripts that share a basename (e.g. both ``run.py``) must land at
        distinct files; the second becomes ``run_1.py``, the third ``run_2.py`` -- so
        ``reproduce.py`` drives each independently. Mutates ``used`` to record the choice.
        """
        if name not in used:
            used.add(name)
            return name
        stem, dot, ext = name.partition(".")
        suffix = f".{ext}" if dot else ""
        i = 1
        while f"{stem}_{i}{suffix}" in used:
            i += 1
        chosen = f"{stem}_{i}{suffix}"
        used.add(chosen)
        return chosen

    def _emit_reproduction_bundle(
        self,
        listings: Sequence[ReproListing],
        paper_dir: Path,
        spec_id: str,
    ) -> None:
        """Land ``paper/code/`` + ``paper/reproduce.py`` for the F3 runnable bundle (§3).

        The compiler is the SOLE filesystem toucher: it copies each resolvable script's
        recorded body into ``paper/code/<filename>`` and writes the pure
        :func:`render_reproduce_driver` text to ``paper/reproduce.py``. The bundle is
        written ONLY when there is something to drive (at least one ``ReproListing``); an
        entirely ``code_ref``-free run passes ``[]`` and NOTHING is written -- the run's
        ``paper/`` stays byte-identical to today (the F3 regression invariant). A
        pointer-only run still writes ``reproduce.py`` (documenting the commits) but no
        ``paper/code/`` files.
        """
        if not listings:
            return
        scripts = [it for it in listings if it.is_script]
        if scripts:
            code_dir = paper_dir / "code"
            code_dir.mkdir(parents=True, exist_ok=True)
            for it in scripts:
                # text/filename are guaranteed non-None for a script ReproListing.
                (code_dir / (it.filename or "")).write_text(
                    it.text or "", encoding="utf-8"
                )
        driver = render_reproduce_driver(listings, spec_id)
        (paper_dir / "reproduce.py").write_text(driver, encoding="utf-8")

    def _collect_contested_checkpoints(
        self, spec: Spec, claims: Sequence[Claim]
    ) -> List[ContestedCheckpoint]:
        """Surface a contested checkpoint per hypothesis whose Claim is CONTESTED and
        which still lacks a CONTESTED_RECORD (read-only; ``contested_open`` keys on the
        record just written, so a re-compile after ``record_contested`` surfaces nothing).
        """
        out: List[ContestedCheckpoint] = []
        for claim in claims:
            if claim.status != ClaimStatus.CONTESTED:
                continue
            if contested_open(spec, claim.answers, self.workspace_dir):
                out.append(
                    contested_checkpoint(spec, claim.answers, spec.version)
                )
        return out

    def _collect_novelty_checkpoints(
        self, spec: Spec, claims: Sequence[Claim], evidence: Sequence[EvidenceItem]
    ) -> List[NoveltyCheckpoint]:
        """Surface a reason-tailored novelty checkpoint per {hypothesis, kind} whose
        ``novelty_{kind}`` flag is set and whose ``claim-novelty-{kind}-<hyp>`` is PROPOSED
        (NON-HALT, 2-kind; ``novelty_open`` keys on the kind's novelty claim just persisted,
        so a re-compile after a found_nothing decision for that kind -- which makes the
        claim SUPPORTED -- surfaces nothing).

        Iterates the SPEC hypotheses x kinds (not ``claims``): a flagged novelty kind is
        open even with no experiment claim, exactly as the novelty pass in ClaimUpdater
        persists its per-kind novelty claim independently of experiment evidence.

        The reason is derived per kind from the SAME in-memory ``evidence`` the kind's
        novelty claim was derived from (``novelty_reason_from_decisions(h.id, kind, ...)``
        over the NOVELTY_DECISIONs in ``evidence``), NOT from disk: in a single-pass
        ``compile()`` an in-memory found_something decision is not yet persisted, so a disk
        read would emit the wrong (not_searched / "go search") prompt. ``novelty_open``
        reads the just-persisted kind novelty CLAIM status, which IS on disk -- correct.
        """
        novelty_decisions = [
            ev for ev in evidence if ev.kind == EvidenceKind.NOVELTY_DECISION
        ]
        out: List[NoveltyCheckpoint] = []
        for h in spec.hypotheses:
            for kind in _NOVELTY_KINDS:
                if novelty_open(spec, h.id, kind, self.workspace_dir):
                    reason = novelty_reason_from_decisions(
                        h.id, kind, novelty_decisions
                    )
                    out.append(
                        novelty_checkpoint(
                            spec, h.id, kind, spec.version, reason=reason
                        )
                    )
        return out

    @staticmethod
    def _collect_checkpoints(
        spec: Spec,
        evidence: Sequence[EvidenceItem],
    ) -> List[Checkpoint]:
        """Flag every proof/qualitative hypothesis as an agent checkpoint,
        attaching any evidence finding that bears on it for the agent to judge."""
        checkpoints: List[Checkpoint] = []
        for h in spec.hypotheses:
            if h.decision_rule.kind not in _NON_NUMERIC:
                continue
            findings = [
                ev.result.finding
                for ev in evidence
                if ev.result.finding
                and any(b.target_id == h.id for b in ev.bears_on)
            ]
            checkpoints.append(
                Checkpoint(
                    hypothesis_id=h.id,
                    kind=h.decision_rule.kind.value,
                    expression=h.decision_rule.expression,
                    finding="\n".join(findings),
                    spec_version=spec.version,
                )
            )
        return checkpoints

    @staticmethod
    def _save_spec(spec: Spec, run_dir: Path) -> None:
        (run_dir / "spec.json").write_text(
            json.dumps(spec.model_dump(mode="json"), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    @staticmethod
    def _save_prior_work_checkpoint(
        checkpoint: PriorWorkCheckpoint, run_dir: Path
    ) -> None:
        """Persist the prior_work checkpoint as ``checkpoints/prior_work.json``.

        It shares the ``checkpoints/`` directory with the judge ``<hyp-id>.json``
        files but is distinguishable on disk by its ``checkpoint_type`` discriminator
        (and by the fixed ``prior_work.json`` name) -- decision vs judgment never
        get confused (the discriminated-union contract in loop/verdict.py).
        """
        cp_dir = run_dir / "checkpoints"
        cp_dir.mkdir(parents=True, exist_ok=True)
        (cp_dir / "prior_work.json").write_text(
            json.dumps(checkpoint.model_dump(mode="json"), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    @staticmethod
    def _save_science_findings(
        findings: Sequence[ScienceFinding], run_dir: Path
    ) -> None:
        """Persist the spec-gate science audit to ``checkpoints/science.json`` (+ a Markdown
        view), a recording-type artifact alongside ``prior_work.json``.

        ALWAYS written (even when empty) so ``science.json`` unambiguously records that the
        audit ran: an absent file means a pre-science-guards run, an empty ``findings`` list
        means audited-and-clean. Never halts -- the findings are reminders the author resolves
        by a Spec amendment (design/science-guards.md).
        """
        cp_dir = run_dir / "checkpoints"
        cp_dir.mkdir(parents=True, exist_ok=True)
        (cp_dir / "science.json").write_text(
            json.dumps(
                {"findings": [f.model_dump(mode="json") for f in findings]},
                indent=2, ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        if findings:
            lines = ["# Spec-gate science findings (design/science-guards.md)", ""]
            lines.append("Structural weak-science patterns detected at spec-compile time "
                         "(NEVER a halt). Resolve each by a Spec amendment (supply the "
                         "missing artifact or a justification), then re-init/amend.")
            lines.append("")
            for f in findings:
                tag = f.hypothesis_id or "(spec-wide)"
                lines.append(f"## {f.guard} -- {tag}")
                lines.append(f"- {f.message}")
                lines.append("")
            (run_dir / "science.md").write_text("\n".join(lines), encoding="utf-8")

    @staticmethod
    def _save_checkpoints(checkpoints: Sequence[Checkpoint], run_dir: Path) -> None:
        """Persist checkpoints as typed JSON (the contract) AND a Markdown view.

        F1 (design/rigor-shell-architecture.md §4.3): ``checkpoints/<hyp-id>.json``
        is the round-trippable contract; ``checkpoints.md`` is rendered *from* it as
        a human-facing prompt (the inverse of the milestone-1 prose-primary layout).
        """
        cp_dir = run_dir / "checkpoints"
        cp_dir.mkdir(parents=True, exist_ok=True)
        for c in checkpoints:
            model = c.to_model()
            (cp_dir / f"{c.hypothesis_id}.json").write_text(
                json.dumps(model.model_dump(mode="json"), indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        (run_dir / "checkpoints.md").write_text(
            _render_checkpoints_view(checkpoints), encoding="utf-8"
        )


def _render_checkpoints_view(checkpoints: Sequence[Checkpoint]) -> str:
    """Render the human-facing ``checkpoints.md`` view from typed checkpoints (F1).

    The typed ``checkpoints/<hyp-id>.json`` files are the contract; this prose is a
    generated prompt for the in-session agent that authors the matching
    ``verdicts/<hyp-id>.json`` (no autonomous LLM call).
    """
    lines = ["# Agent judgment checkpoints", ""]
    lines.append("proof/qualitative hypotheses awaiting an in-session agent "
                 "verdict (no autonomous LLM call). For each, author "
                 "verdicts/<hyp-id>.json with the chief-over-N trail, then "
                 "re-enter the loop (sci-adk resolve <run-dir>).")
    lines.append("")
    for c in checkpoints:
        lines.append(f"## {c.hypothesis_id} ({c.kind})")
        lines.append(f"- Criterion: {c.expression}")
        lines.append(f"- Finding: {c.finding or '_(no experiment finding yet)_'}")
        lines.append("")
    return "\n".join(lines)
