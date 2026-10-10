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
import hashlib
import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from sci_adk.core.claim import Claim, ClaimStatus
from sci_adk.core.evidence import EvidenceItem, EvidenceKind
from sci_adk.core.parser import ProposalParser
from sci_adk.core.spec import DecisionRuleKind, Spec
from sci_adk.core.spec_science import ScienceFinding, audit_spec_science
from sci_adk.loop.claim_updater import ClaimUpdater, _NOVELTY_KINDS
from sci_adk.loop.code_ref import (
    NON_REPRODUCIBLE_KINDS,
    code_ref_data_files,
    describe_data_mismatch,
    describe_mismatch,
    resolve_code_ref_data_files,
    resolve_code_ref_scripts,
)
from sci_adk.loop.judge import Judge
from sci_adk.loop.literature_triggers import (
    contested_checkpoint,
    contested_open,
    novelty_checkpoint,
    novelty_open,
    novelty_reason_from_decisions,
)
from sci_adk.loop.prior_work import (
    PriorWorkHalt,
    prior_work_checkpoint,
    prior_work_open,
)
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
from sci_adk.render.authored_si import render_authored_si_latex
from sci_adk.render.bib_latex import paper_bib
from sci_adk.render.novelty import (
    NOVELTY_SENTENCES_FILE,
    NoveltySentence,
    novelty_sentences_payload,
    parse_novelty_sentences,
)
from sci_adk.render.paper import render_paper_latex, run_font_policy
from sci_adk.render.pkgreqs_checks import bib_subset, cited_keys
from sci_adk.render.prose import AuthoredSI, PaperProse, SIProse
from sci_adk.render.reproduction import (
    ReproListing,
    ReproScript,
    bundle_file_names,
    bundle_scripts,
    listed_code_files,
    reader_summary,
    reader_text,
    render_reproduce_driver,
    written_by_sci_adk,
)
from sci_adk.render.si import render_si_latex

# An experiment hook turns a Spec into Evidence (e.g. by running code in Docker).
ExperimentFn = Callable[[Spec, Path], Sequence[EvidenceItem]]

# SPEC-SI-AUTHORING-001 REQ-SA-202: the deterministic record dump's relocation target.
# The run dir IS the deposit (``runs/<spec.id>/``); the retained deterministic record
# artifact lives at its root as ``record.tex`` -- OUTSIDE ``paper/`` (which now holds the
# BELIEF submission documents ``draft.tex``/``si.tex``). Keeping it out of ``paper/`` makes
# the record EXEMPT from the per-run tool-vocab gate BY CONSTRUCTION (that gate scans only
# ``paper/`` documents; REQ-SA-206 / AC-B6) and gives the M2 deposit-completeness checker a
# single source of truth for where the record artifact lives.
RECORD_ARTIFACT_NAME: str = "record.tex"


# @MX:ANCHOR: [AUTO] the canonical deposit path for the deterministic record artifact;
#   the compiler writes it and the M2 deposit-completeness checker reads it (single source).
# @MX:REASON: [AUTO] REQ-SA-202 (F4) -- one source of truth for the relocation target so
#   the record/belief boundary (record.tex in the deposit, si.tex in paper/) cannot drift.
def deposit_record_path(run_dir: Path) -> Path:
    """The deposit path of the retained deterministic record artifact for ``run_dir``.

    ``run_dir`` is the run's deposit (``runs/<spec.id>/``); the record artifact is
    ``run_dir/record.tex`` -- the SINGLE SOURCE both the compiler (which writes it,
    REQ-SA-202) and the deposit-completeness check (M2, REQ-SA-301) reference.
    """
    return run_dir / RECORD_ARTIFACT_NAME

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
    # SPEC-SI-AUTHORING-001 REQ-SA-202: the deposit's retained deterministic record
    # artifact (record.tex). The dump that used to occupy si_path lives here now.
    record_path: Optional[Path] = None
    prior_work_checkpoint: Optional[PriorWorkCheckpoint] = None
    contested_checkpoints: List[ContestedCheckpoint] = field(default_factory=list)
    novelty_checkpoints: List[NoveltyCheckpoint] = field(default_factory=list)
    figure_consistency: Optional[FigureConsistencyReport] = None
    science_findings: List[ScienceFinding] = field(default_factory=list)

    @property
    def needs_agent(self) -> bool:
        """True when proof/qualitative checkpoints await an in-session verdict."""
        return bool(self.checkpoints)


def _listing_text(raw: bytes) -> Optional[str]:
    """A shipped script's body as text for the record listing, or None (not UTF-8).

    Line ends are normalized as ``Path.read_text`` does; the shipped copy keeps the bytes.
    """
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return None
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _output_name(output_ref: str) -> str:
    """The file name of the first path in a recorded output reference, or ``""``: the
    summary a reader sees when the finding's first sentence is nothing but references."""
    token = (output_ref or "").split(None, 1)[0] if (output_ref or "").strip() else ""
    token = token.rstrip(";,")
    return token.replace("\\", "/").rsplit("/", 1)[-1] if token else ""


def _plain_file_name(name: str) -> bool:
    """Whether ``name`` is a bare file name (no directory part, not ``.``/``..``)."""
    return (
        bool(name)
        and name not in (".", "..")
        and "/" not in name
        and "\\" not in name
        and Path(name).name == name
    )


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
        # The code_ref hash mismatches found by the most recent render (one line each:
        # evidence id, file, recorded vs actual sha256). Such an item is never shipped as the
        # recorded script; the CLI prints these as warnings.
        self.code_ref_warnings: List[str] = []
        self.code_ref_data_warnings: List[str] = []

    def compile(
        self,
        proposal_text: str,
        *,
        spec_id: Optional[str] = None,
        spec: Optional[Spec] = None,
        experiment: Optional[ExperimentFn] = None,
        prose: Optional[PaperProse] = None,
        si_prose: Optional[SIProse] = None,
        si: Optional[AuthoredSI] = None,
        figures: Optional[Sequence[AnyFigure]] = None,
        si_figures: Optional[Sequence[AnyFigure]] = None,
        enforce_prior_work: bool = False,
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
                spirit as ``prose``. Absent -> the record dump is byte-identical to the
                no-prose dump.
            si: optional AUTHORED Supporting Information -- the belief artifact ② (the
                overflow of ``main.tex``), rendered to ``paper/si.tex`` via
                ``render_authored_si_latex`` (SPEC-SI-AUTHORING-001 Pillar A / M4). When
                supplied, the authored ``si.tex`` is emitted alongside ① ``draft.tex`` and ③
                the deposit ``record.tex``; when absent, NO ``paper/si.tex`` is written (a
                thin/absent SI is permitted, REQ-SA-107). Never LLM-generated -- input, the
                same spirit as ``prose``. Distinct from ``si_prose`` (which wraps the record
                dump): ``si`` is the authored overflow that REPLACES the dump in the
                ``paper/si.tex`` slot.
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

        # Proactive prior-work enforcement (opt-in; the orchestrated "start research" path
        # -- the `run` verb -- sets this). The raw library/primitive default is False so
        # direct compile()/test callers are unaffected. When on and no prior-work DECISION
        # is recorded yet, refuse to run experiments: the researcher searches (or records a
        # skip-with-reason) FIRST. stage_init_spec has already laid down the run dir + spec,
        # so the human can record the decision and re-run. Not a search mandate -- a decision
        # mandate (design/literature-acquisition.md: the discovery decision must be recorded).
        if enforce_prior_work and prior_work_open(spec, self.workspace_dir):
            raise PriorWorkHalt(spec.id, self.workspace_dir / "runs" / spec.id)

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

        paper_path, si_path, record_path, figure_consistency = self.stage_render(
            spec,
            evidence=evidence,
            claims=claims,
            checkpoints=checkpoints,
            prose=prose,
            si_prose=si_prose,
            si=si,
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
            # SPEC-SI-AUTHORING-001 M4: the paper/si.tex slot (freed in M1) now carries the
            # AUTHORED overflow ② when an AuthoredSI is supplied; si_path points at it then,
            # else None (a thin/absent SI). record_path always points at the deposit record ③.
            si_path=si_path,
            record_path=record_path,
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
        si: Optional[AuthoredSI] = None,
        figures: Optional[Sequence[AnyFigure]] = None,
        si_figures: Optional[Sequence[AnyFigure]] = None,
    ) -> tuple[Path, Optional[Path], Optional[Path], Optional[FigureConsistencyReport]]:
        """Render the ``paper/`` belief artifacts (``draft.tex`` + optional authored
        ``si.tex`` + figures + bib) and the deposit's deterministic ``record.tex`` (the
        ``render`` verb's stage).

        SPEC-SI-AUTHORING-001:
          - M1: the deterministic dump is RELOCATED to the deposit as ``record.tex``
            (REQ-SA-202); the THIRD tuple element is that record path.
          - M4: when an ``AuthoredSI`` is supplied, the freed ``paper/si.tex`` slot carries
            the AUTHORED overflow ② rendered via ``render_authored_si_latex`` (the prose
            pipeline, NOT the dump); the SECOND tuple element is that si.tex path. When ``si``
            is absent, NO ``paper/si.tex`` is written (a thin/absent SI, REQ-SA-107) and the
            second element is ``None``. This is the end-to-end emit of the three correctly-
            typed artifacts: ① ``draft.tex`` (authored) · ② ``si.tex`` (authored) · ③
            ``record.tex`` (the deposit record).

        The MAIN figures (``figures``) appear ONLY in the paper's Results; the SI carries
        only ``si_figures`` (supplementary, default none) -- so a main figure is never
        duplicated across the two documents (design feedback 5.2). Each document has its OWN
        independent bibliography (SPEC-SI-AUTHORING-001 M6): ``draft.tex`` wires the full
        co-located ``references.bib`` (the pool), the authored ``si.tex`` wires a cited-only
        ``references_SI.bib`` subset of that same pool (REQ-SA-604/607) -- never a shared
        ``\\bibliography``.

        Loads Evidence, Claims, and the judge checkpoints from disk when not supplied
        (the verb path); the chained ``compile`` passes the in-memory values
        (byte-identical to the monolith). The render itself is pure (data in, string
        out); this stage is the composition root that locates the citations + bib and
        co-locates figure/bib sources into ``paper/`` for Overleaf self-containment.

        Returns ``(paper_path, si_path, record_path, figure_consistency)`` -- ``si_path`` is
        ``None`` when no ``AuthoredSI`` was supplied.
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

        # A render without an SI writes no paper/si.tex, so one from an earlier render stays
        # in place; the bindings of its novelty sentences are carried into the side file
        # below. Read BEFORE anything is written: an unreadable side file stops the render.
        kept_si_bindings = self._kept_si_bindings(run_dir, spec.id) if si is None else []

        # Citations + bibliography are gathered for the run (renderers stay pure --
        # data in, string out; the compiler is the composition root that locates them).
        # A hypothesis whose MAIN experiment Claim is already RESOLVED (SUPPORTED/REFUTED) is
        # no longer "pending". Drop its checkpoint from the rendered belief paper so a
        # fully-resolved run carries NO "Pending agent judgments" section -- whose boilerplate
        # ("verdict") and dumped finding digits would otherwise trip the tool-vocabulary and
        # number-audit gates on the run's OWN auto-generated scaffolding. The judge-checkpoint
        # FILES on disk are untouched; this filters only what the paper renders as still-open.
        # Match on the MAIN claim id (``claim-<hyp>``), NOT ``Claim.answers``: the per-kind
        # novelty claims (``claim-novelty-<kind>-<hyp>``) share ``answers == hyp`` and must
        # not mark a hypothesis resolved when only a novelty axis -- not the experiment claim
        # the checkpoint tracks -- has been decided.
        pending_dicts = self._open_checkpoints(claims_list, checkpoints_list)
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
        # Each \novelty assertion renders as its plain sentence; the renderers hand back the
        # {document, kind, hyp, sentence} bindings, written beside the paper below.
        novelty_found: List[NoveltySentence] = []
        # One text face for the submission: decided from the draft's AND the authored SI's
        # figures, so draft.tex and si.tex always share text_font_lines.
        font_policy = run_font_policy(figures, si.figures if si is not None else [])
        paper_tex = render_paper_latex(
            spec, claims_list, evidence_list,
            pending=pending_dicts,
            prose=prose,
            cited_dois=cited_dois,
            bib_path=bib_path,
            figures=figures,
            novelty_sentences=novelty_found,
            font_policy=font_policy,
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

        # AUTHORED si.tex (SPEC-SI-AUTHORING-001 M4, REQ-SA-101/202): when an AuthoredSI is
        # supplied, the freed paper/si.tex slot carries the AUTHORED overflow ② -- rendered
        # through render_authored_si_latex (the REUSED prose pipeline: factref fidelity +
        # \novelty gate + the sanitizer), NOT the deterministic dump (which lands in the
        # deposit record.tex below). The render is pure + FAIL-LOUD (an unbacked \evval raises
        # ValueError, record fidelity); the compiler only writes the returned string. When
        # si is None NOTHING is written -- a thin/absent SI is permitted (REQ-SA-107) and the
        # paper/si.tex slot stays empty (backward compatible with M1). This is the single
        # end-to-end wiring point that fills ② alongside ① (above) and ③ (below).
        si_path: Optional[Path] = None
        if si is not None:
            # SPEC-SI-AUTHORING-001 M6 (REQ-SA-604/605/606): the authored si.tex gets its OWN
            # cited-only references_SI.bib -- a SUBSET of the run's ONE literature pool, NOT a
            # separate acquisition. D2 ordering (no circularity): the cited keys are read from
            # the authored SI SOURCE (the AuthoredSI section bodies) BEFORE the render -- valid
            # because \cite survives the _slot pipeline verbatim, so source cited keys == rendered
            # cited keys. Then filter the pool to those keys, co-locate the subset, and pass its
            # path to the SINGLE render. D6 ABSENCE: no pool OR no cited keys -> write NO file and
            # pass no bib_path (mirrors the main paper's missing-pool handling), so si.tex emits
            # no \bibliography. A cited key absent from the pool is NOT silently dropped -- it
            # cannot be in the subset, so the SI cite gate (verify) surfaces it.
            si_bib_path = self._colocate_si_bib(run_dir, paper_dir, si)
            # The SI is set in the draft's faces (the run's one font policy, above).
            si_tex = render_authored_si_latex(
                si, spec, claims_list, evidence_list, bib_path=si_bib_path,
                novelty_sentences=novelty_found,
                draft_font_policy=font_policy,
            )
            if si_tex is not None:
                si_path = paper_dir / "si.tex"
                si_path.write_text(si_tex, encoding="utf-8")

        self._write_novelty_sentences(run_dir, spec.id, novelty_found + kept_si_bindings)

        # F3 reproduction bundle (design/paper-publishing-requirements.md §3): resolve every
        # script each Evidence item's provenance.code_ref names (or a bare-ref pointer),
        # then (a) inline each distinct script once in the record's "Reproduction code"
        # section, (b) ship one copy per distinct script into paper/code/, and (c) write
        # paper/reproduce.py (a manifest + hash check; it runs nothing).
        # The compiler -- the SOLE filesystem toucher -- does the resolution + fs; the
        # renderer stays pure (it receives the resolved listings). When NO Evidence item
        # carries a code_ref, repro_listings is empty -> no section, no paper/code/, no
        # reproduce.py (the run's paper/ is byte-identical to today; the F3 regression
        # invariant). Resolution is fail-open: a bare commit ref is a POINTER, never an error.
        repro_listings = self._resolve_repro_listings(evidence_list, run_dir)

        # The deposit record.tex (SPEC-SI-AUTHORING-001 M1) -- the SAME writer the
        # record-only render uses, so the two cannot drift.
        record_path = self._write_record(
            spec, claims_list, evidence_list, run_dir,
            repro_listings=repro_listings, figures=si_figures, prose=si_prose,
            bib_path=bib_path,
        )

        # Land the bundle (paper/code/ + paper/reproduce.py). paper/code/ is written only when
        # at least one named script resolved; a pointer-only set (every code_ref a bare
        # commit) still lists the references in reproduce.py; an entirely code_ref-free run
        # writes nothing (byte-identical paper/). A re-render removes the paper/code/ files
        # the previous render wrote and this one does not. See _emit_reproduction_bundle.
        self._emit_reproduction_bundle(repro_listings, paper_dir, spec.id)

        # Prose<->figure ref consistency (design/paper-figures-and-si.md D4): scan the
        # RENDERED body for \ref{fig:...}/\label integrity. NON-BLOCKING -- surfaced in
        # the result (a warning channel, like the contested/novelty checkpoints), never
        # a hard fail (the verify-style gate is Phase 3). figure_labels enforces unique
        # ids; rendering above would already have raised on a missing evidence id.
        figure_consistency = check_figure_consistency(
            figure_labels(figures), paper_tex
        )
        return paper_path, si_path, record_path, figure_consistency

    def stage_render_record(
        self,
        spec: Spec,
        *,
        evidence: Optional[Sequence[EvidenceItem]] = None,
        claims: Optional[Sequence[Claim]] = None,
    ) -> Path:
        """Deposit ONLY the deterministic record ``record.tex`` (``render --record-only``).

        The first half of the two-session publish protocol: the session that ran the
        experiments deposits the record and stops; a later session writes the paper from
        it. A full :meth:`stage_render` with no prose would also write a skeleton
        ``paper/draft.tex``, which ``verify`` judges as the conclusion-bearing manuscript
        and fails against a frozen ``pubreqs.json`` -- so this stage writes NOTHING under
        ``paper/`` (no draft, no SI, no figures, no bib copy, no ``reproduce.py``).

        ``record.tex`` is byte-identical to the one a full render writes for the same
        record: both go through :meth:`_write_record`, and the record's only external
        reference -- ``\\bibliography{references}`` -- is emitted from the bib's stem, which
        is ``references`` whether the path is the run's own ``references.bib`` (here) or its
        ``paper/`` copy (the full render). Figures in the record come only from the
        library-only ``si_figures`` (never passed here), and reproduction code is inlined
        verbatim, so the record references no file under ``paper/``.

        Returns the ``record.tex`` path.
        """
        evidence_list = (
            list(evidence) if evidence is not None else self._load_evidence(spec)
        )
        claims_list = list(claims) if claims is not None else self._load_claims(spec)
        run_dir = self.workspace_dir / "runs" / spec.id
        return self._write_record(
            spec, claims_list, evidence_list, run_dir,
            repro_listings=self._resolve_repro_listings(evidence_list, run_dir),
            figures=None, prose=None, bib_path=self._locate_bib_path(run_dir),
        )

    def render_texts(
        self,
        spec: Spec,
        *,
        prose: Optional[PaperProse] = None,
        si: Optional[AuthoredSI] = None,
        figures: Optional[Sequence[AnyFigure]] = None,
    ) -> tuple[str, Optional[str]]:
        """The ``draft.tex`` and authored ``si.tex`` text :meth:`stage_render` would write
        for these inputs -- written nowhere.

        For ``sci-adk numbers draft`` (design/declared-numbers.md §4.4), which must read the
        paper exactly as render will produce it before render has run: the same recorded
        Evidence and Claims, the same still-open checkpoints, the same pure renderers and
        sanitizer. The bibliography is located rather than co-located; its stem -- all the
        renderer uses -- is the same, so the text is byte-identical to what render writes.
        Returns ``(draft_tex, si_tex)``; ``si_tex`` is ``None`` when ``si`` is.

        Raises:
            ValueError: a fact macro the record cannot back, or a malformed figure spec
                (the renderers fail loud, exactly as in a render).
        """
        evidence_list = self._load_evidence(spec)
        claims_list = self._load_claims(spec)
        checkpoints_list = self._load_checkpoints(spec, evidence_list)
        run_dir = self.workspace_dir / "runs" / spec.id
        figures = list(figures or [])
        font_policy = run_font_policy(figures, si.figures if si is not None else [])
        draft_tex = render_paper_latex(
            spec, claims_list, evidence_list,
            pending=self._open_checkpoints(claims_list, checkpoints_list),
            prose=prose,
            cited_dois=self._gather_cited_dois(evidence_list, run_dir),
            bib_path=self._locate_bib_path(run_dir),
            figures=figures,
            font_policy=font_policy,
        )
        si_tex: Optional[str] = None
        if si is not None:
            si_bib = (
                str(run_dir / "paper" / "references_SI.bib")
                if self._si_bib_subset(run_dir, si) else None
            )
            si_tex = render_authored_si_latex(
                si, spec, claims_list, evidence_list, bib_path=si_bib,
                draft_font_policy=font_policy,
            )
        return draft_tex, si_tex

    @staticmethod
    def _open_checkpoints(
        claims: Sequence[Claim], checkpoints: Sequence["Checkpoint"]
    ) -> List[dict]:
        """The checkpoints a rendered paper still lists as pending (see :meth:`stage_render`).

        A hypothesis whose MAIN experiment Claim (``claim-<hyp>``) is SUPPORTED or REFUTED is
        no longer pending; novelty sub-claims share ``answers`` and must not count.
        """
        resolved_main_claim_ids = {
            c.id for c in claims if c.is_supported() or c.is_refuted()
        }
        return [
            c.__dict__ for c in checkpoints
            if f"claim-{c.hypothesis_id}" not in resolved_main_claim_ids
        ]

    @staticmethod
    def _write_record(
        spec: Spec,
        claims: Sequence[Claim],
        evidence: Sequence[EvidenceItem],
        run_dir: Path,
        *,
        repro_listings: Sequence[ReproListing],
        figures: Optional[Sequence[AnyFigure]],
        prose: Optional[SIProse],
        bib_path: Optional[str],
    ) -> Path:
        """Write the deposit's ``record.tex`` (SPEC-SI-AUTHORING-001 M1) and return its path.

        The ONE writer of the record, shared by :meth:`stage_render` and
        :meth:`stage_render_record`. A STANDALONE document: every Evidence item, the numeric
        data tables, the supplementary figures, the inlined reproduction code, and the
        verdicts with their frozen decision rules. It lives at the run root via
        ``deposit_record_path`` -- OUTSIDE ``paper/``, which holds the belief documents --
        so the per-run tool-vocabulary gate never scans it (REQ-SA-206, by construction).
        ``render_si_latex`` is reused verbatim (REQ-SA-201).

        ``digest=None`` on purpose: at compile time the Evidence may not yet be persisted
        (the loop persists AFTER compile), so a digest here would cover an incomplete run
        dir; the record's integrity section points to ``sci-adk verify`` instead.
        ``paper_body=None``: the record is standalone, so its figures are numbered in supply
        order.
        """
        record_tex = render_si_latex(
            spec, claims, evidence, figures=figures, digest=None,
            prose=prose, paper_body=None, bib_path=bib_path,
            repro_listings=repro_listings,
        )
        record_path = deposit_record_path(run_dir)
        record_path.write_text(record_tex, encoding="utf-8")
        return record_path

    @staticmethod
    def _kept_si_bindings(run_dir: Path, spec_id: str) -> List[NoveltySentence]:
        """The ``si.tex`` novelty bindings to carry over when a render has no SI.

        Such a render writes no ``paper/si.tex``, so the one an earlier render wrote stays
        in place, still printing that render's novelty sentences. Rewriting the side file
        from the draft alone would leave those sentences unbound and unchecked, so their
        bindings are read back here and written again with the draft's. No ``si.tex`` or no
        side file -> nothing to keep.

        Raises:
            ValueError: ``si.tex`` stays but the side file cannot be read (raised before the
                render writes anything, instead of dropping the bindings).
        """
        side = run_dir / NOVELTY_SENTENCES_FILE
        if not (run_dir / "paper" / "si.tex").is_file() or not side.is_file():
            return []
        try:
            kept = parse_novelty_sentences(
                json.loads(side.read_text(encoding="utf-8")), spec_id
            )
        except ValueError as exc:  # json.JSONDecodeError is a ValueError
            raise ValueError(
                f"paper/si.tex from an earlier render stays in place (this render has no "
                f"SI), but the bindings of its novelty sentences in "
                f"{NOVELTY_SENTENCES_FILE} cannot be read: {exc}. Re-render with the SI, "
                f"which rebinds them."
            ) from exc
        return [s for s in kept if s.document == "si.tex"]

    @staticmethod
    def _write_novelty_sentences(
        run_dir: Path, spec_id: str, sentences: Sequence[NoveltySentence]
    ) -> Optional[Path]:
        """Write the rendered novelty bindings to ``run_dir/novelty_sentences.json``.

        The paper carries each novelty assertion as a plain sentence; this side file --
        beside ``spec.json`` / ``declarations.json``, outside ``paper/``, never submitted --
        is what binds each sentence to the {kind, hypothesis} the record must back, for
        ``verify`` to re-derive. ``sentences`` are this render's bindings plus, when it had
        no SI, those of the ``si.tex`` it left in place (:meth:`_kept_si_bindings`). Written
        when there is a binding. When there is none, an existing file from an earlier
        render is rewritten with an empty list (a stale binding would describe a paper that
        no longer exists); with no earlier file nothing is written, so a novelty-free run
        gains no file.
        """
        path = run_dir / NOVELTY_SENTENCES_FILE
        if not sentences and not path.is_file():
            return None
        payload = novelty_sentences_payload(spec_id, sentences)
        path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        return path

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
          (b) the run's literature ``manifest.csv`` (see ``_LITERATURE_DIRS``; the shape
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
        manifest = ResearchCompiler._literature_file(run_dir, "manifest.csv")
        if manifest is not None:
            try:
                with manifest.open(encoding="utf-8", newline="") as fh:
                    for row in csv.DictReader(fh):
                        _add(row.get("doi"))
            except (OSError, csv.Error):
                pass

        return seen

    # Where a run's literature lives, in lookup order: ``literature/`` is where
    # LiteratureAcquirer writes (literature_acquirer.py, ``self.literature_dir``);
    # ``artifacts/literature/`` is the older layout some runs and fixtures still use.
    _LITERATURE_DIRS: tuple[tuple[str, ...], ...] = (
        ("literature",),
        ("artifacts", "literature"),
    )

    @staticmethod
    def _literature_file(run_dir: Path, name: str) -> Optional[Path]:
        """The run's literature file ``name`` from the first layout that has it, or None."""
        for parts in ResearchCompiler._LITERATURE_DIRS:
            path = run_dir.joinpath(*parts, name)
            if path.is_file():
                return path
        return None

    @staticmethod
    def _locate_bib_path(run_dir: Path) -> Optional[str]:
        """Return the run's ``references.bib`` path when present (see ``_LITERATURE_DIRS``).

        The renderer wires an EXISTING ``.bib`` (it never generates one); this just
        locates it. ``None`` when absent -> the renderer emits no ``\\bibliography``.
        """
        bib = ResearchCompiler._literature_file(run_dir, "references.bib")
        return str(bib) if bib is not None else None

    @classmethod
    def _colocate_bib(cls, run_dir: Path, paper_dir: Path) -> Optional[str]:
        """Copy the run's ``references.bib`` next to ``draft.tex`` and return its path.

        Overleaf self-containment: when ``_locate_bib_path`` finds the run's
        ``references.bib`` (see ``_LITERATURE_DIRS``), write its LaTeX-safe copy
        (:func:`paper_bib`: HTML entities and tags to LaTeX, bare specials escaped,
        characters pdflatex cannot typeset through the prose map or accent commands; title case
        protected, no ISSN or URL repeating the DOI, name letters as LaTeX commands; keys and
        doi values untouched) to ``paper/references.bib`` so
        uploading the ``paper/`` folder as-is resolves ``\\bibliography{references}`` and
        compiles. The literature store is only read -- it keeps the bytes it was acquired
        with. The returned path's stem is ``references``, so the (pure) renderer emits
        exactly that ``\\bibliography`` key. ``None`` when no source ``.bib`` exists -> the
        renderer emits no ``\\bibliography``. No entry is generated or dropped.
        """
        src = cls._locate_bib_path(run_dir)
        if src is None:
            return None
        dest = paper_dir / "references.bib"
        try:
            pool = Path(src).read_text(encoding="utf-8")
        except UnicodeDecodeError:
            # Not UTF-8, so not something to rewrite character by character: copied as is.
            shutil.copyfile(src, dest)
            return str(dest)
        dest.write_text(paper_bib(pool), encoding="utf-8")
        return str(dest)

    @classmethod
    def _colocate_si_bib(
        cls, run_dir: Path, paper_dir: Path, si: AuthoredSI
    ) -> Optional[str]:
        """Build + co-locate the cited-only ``paper/references_SI.bib`` (M6, REQ-SA-604/606).

        The authored SI's OWN bibliography, SYMMETRIC to :meth:`_colocate_bib` for the main
        paper but with a SUBSET filter: the pool entries whose key is CITED in the SI. D2
        ordering (no ``bib_path``<->``cited_keys`` circularity): the cited keys are read from
        the authored SI SOURCE (the ``AuthoredSI`` section bodies) here, BEFORE the render --
        valid because ``\\cite`` survives the ``_slot`` pipeline verbatim, so the source cited
        keys equal the rendered cited keys. The pool is the SAME single source
        ``_locate_bib_path`` finds. D6 ABSENCE: no pool OR no cited keys -> write NO file and
        return ``None`` (no ``bib_path`` -> ``si.tex`` emits no ``\\bibliography``, mirroring
        the main paper's missing-pool handling). The subset is a PURE set op (no LLM/network)
        over the pool's LaTeX-safe copy, so each SI entry is byte-identical to its entry in
        ``paper/references.bib``. It never contains a key absent from the pool, so a dangling
        SI cite is left for the verify gate to surface, never silently dropped. Returns the
        co-located path (stem ``references_SI``) or ``None``.
        """
        subset = cls._si_bib_subset(run_dir, si)
        if not subset:
            return None
        dest = paper_dir / "references_SI.bib"
        dest.write_text(subset, encoding="utf-8")
        return str(dest)

    @classmethod
    def _si_bib_subset(cls, run_dir: Path, si: AuthoredSI) -> Optional[str]:
        """The cited-only SI bibliography text (see :meth:`_colocate_si_bib`), or ``None``
        when there is no pool, no cited key, or no cited key in the pool. Writes nothing."""
        src = cls._locate_bib_path(run_dir)
        if src is None:
            return None
        keys = cited_keys("\n".join(s.body for s in si.sections if s.body))
        if not keys:
            return None
        pool = Path(src).read_text(encoding="utf-8")
        return bib_subset(paper_bib(pool), keys) or None

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

        For each item that carries a ``code_ref`` and is not a decision meta-record
        (:data:`NON_REPRODUCIBLE_KINDS` -- a decision pointer, not code), every SOURCE
        script the ``code_ref`` names is resolved with :func:`resolve_code_ref_scripts` --
        the SAME reading verify's F3 gate uses -- DETERMINISTICALLY, no LLM
        (design/paper-publishing-requirements.md §3, OF-4 fail-open). A named script ships
        when its file exists, is readable, and matches its recorded ``sha256=`` (when one is
        recorded); everything else (a bare commit, a missing path, a changed file) is not
        shipped and NEVER an error. The non-source paths it names with a hash are data
        references (:func:`code_ref_data_files`), listed with their hash and never read. An
        item naming no shipped script is a ``pointer`` entry; otherwise a ``script`` entry
        listing its shipped scripts in the order named.

        Shipped scripts are DISTINCT BY CONTENT: one :class:`ReproScript` per sha256 across
        the whole run, holding the exact bytes (so the shipped copy keeps the recorded hash)
        and the text for the record listing. Each is named by its own file name; a name
        shared by different contents gets a ``_<sha256 prefix>`` suffix on every one of them
        (:func:`bundle_file_names`). The bytes are read here (the compiler is the sole
        filesystem toucher; the renderers stay pure).

        A hash mismatch is also collected into ``self.code_ref_warnings`` (one line per
        named script or data file the workspace holds, reset on every call) for the CLI to
        surface.

        Items with no ``code_ref`` contribute nothing -> an entirely code_ref-free run
        yields ``[]`` (the F3 byte-identical regression invariant). First-seen Evidence
        order is preserved (deterministic).
        """
        self.code_ref_warnings = []
        self.code_ref_data_warnings = []
        known_ids = [ev.id for ev in evidence]
        # Pass 1: every named script of every generating-code item, and the distinct
        # contents (sha256 -> (source path, bytes, hash recorded?)) in first-named order.
        contents: Dict[str, Tuple[Path, bytes, bool]] = {}
        items: List[Tuple[EvidenceItem, str, List[str], Tuple[str, ...]]] = []
        for ev in evidence:
            code_ref = (ev.provenance.code_ref or "").strip()
            if not code_ref or ev.kind in NON_REPRODUCIBLE_KINDS:
                continue
            named = resolve_code_ref_scripts(code_ref, run_dir, self.workspace_dir)
            shas: List[str] = []
            for ns in named:
                if ns.resolution.hash_mismatch:
                    # The named file is not the code the record names: never shipped as the
                    # recorded script; surfaced by the CLI.
                    self.code_ref_warnings.append(describe_mismatch(ev.id, ns.resolution))
                script = ns.resolution.script
                if script is None:
                    continue
                try:
                    raw = script.read_bytes()
                except OSError:
                    continue  # unreadable: not shipped (fail-open)
                sha = hashlib.sha256(raw).hexdigest()
                recorded = ns.recorded_sha256 is not None
                if sha not in contents:
                    contents[sha] = (script, raw, recorded)
                elif recorded and not contents[sha][2]:
                    contents[sha] = (contents[sha][0], raw, True)
                if sha not in shas:
                    shas.append(sha)
            for data in resolve_code_ref_data_files(code_ref, run_dir, self.workspace_dir):
                if data.hash_mismatch:
                    # The data file is not the data the result was computed from (verify's
                    # reproduction gate fails on it); surfaced by the CLI.
                    line = describe_data_mismatch(ev.id, data)
                    self.code_ref_warnings.append(line)
                    self.code_ref_data_warnings.append(line)
            unshipped = tuple(
                ns.path for ns in named
                if ns.resolution.script is None and ns.recorded_sha256 is not None
            )
            items.append((ev, code_ref, shas, unshipped))

        names = bundle_file_names(
            [(sha, source.name) for sha, (source, _raw, _rec) in contents.items()]
        )
        shipped = {
            sha: ReproScript(
                filename=names[sha], sha256=sha, hash_recorded=recorded,
                text=_listing_text(raw), data=raw,
            )
            for sha, (_source, raw, recorded) in contents.items()
        }

        out: List[ReproListing] = []
        for ev, code_ref, shas, unshipped in items:
            scripts = tuple(shipped[sha] for sha in shas)
            first = scripts[0] if scripts else None
            # Printed to the bundle's reader, so references a reader cannot resolve (record
            # ids) are removed here too.
            output_ref = reader_text(ev.result.artifact_ref if ev.result else None, known_ids)
            out.append(
                ReproListing(
                    evidence_id=ev.id,
                    code_ref=code_ref,
                    kind="script" if scripts else "pointer",
                    text=first.text if first else None,
                    filename=first.filename if first else None,
                    scripts=scripts,
                    unshipped=unshipped,
                    summary=reader_summary(
                        ev.result.finding if ev.result else None, known_ids,
                        fallback=_output_name(output_ref)
                        or f"a recorded {ev.kind.value.replace('_', ' ')}",
                    ),
                    output_ref=output_ref or None,
                    data_ref=reader_text(ev.provenance.data_ref, known_ids) or None,
                    data_files=tuple(
                        code_ref_data_files(code_ref, run_dir, self.workspace_dir)
                    ),
                )
            )
        return out

    def _emit_reproduction_bundle(
        self,
        listings: Sequence[ReproListing],
        paper_dir: Path,
        spec_id: str,
    ) -> None:
        """Land ``paper/code/`` + ``paper/reproduce.py`` for the F3 bundle (§3).

        The compiler is the SOLE filesystem toucher: it writes each distinct shipped script's
        exact bytes to ``paper/code/<filename>`` and the pure :func:`render_reproduce_driver`
        text to ``paper/reproduce.py``. The bundle is written ONLY when there is something
        to list (at least one ``ReproListing``); an entirely ``code_ref``-free run passes
        ``[]`` and NOTHING is written -- the run's ``paper/`` stays byte-identical to today
        (the F3 regression invariant). A pointer-only run still writes ``reproduce.py``
        (listing the references) but no ``paper/code/`` files.

        A re-render keeps ``paper/code/`` in step with the record: the files the PREVIOUS
        render wrote -- read from the previous ``reproduce.py``'s ``SCRIPTS`` list when a
        sci-adk render wrote that file (:func:`written_by_sci_adk`), never guessed -- that
        this render does not ship are removed (stale duplicates, scripts no longer named).
        Anything else in ``paper/code/`` is the author's and is left alone,
        and so is a listed name that is not a plain file name inside ``paper/code/``. An
        emptied ``paper/code/`` is removed. This pruning runs also when this render has
        nothing to list; the previous ``reproduce.py`` is then removed too, but only when a
        sci-adk render wrote it (:func:`written_by_sci_adk`) -- a hand-written one stays.
        """
        code_dir = paper_dir / "code"
        driver_path = paper_dir / "reproduce.py"
        previous_driver = ""
        if driver_path.is_file():
            try:
                previous_driver = driver_path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                previous_driver = ""
        # Only a reproduce.py a sci-adk render wrote says which paper/code/ files are the
        # render's; the files a hand-written one lists are the author's.
        previously = (
            (listed_code_files(previous_driver) or [])
            if written_by_sci_adk(previous_driver)
            else []
        )
        scripts = bundle_scripts(listings)
        keep = {s.filename for s in scripts}
        for name in previously:
            if name in keep or not _plain_file_name(name):
                continue
            stale = code_dir / name
            if stale.is_file() or stale.is_symlink():
                stale.unlink()
        if scripts:
            code_dir.mkdir(parents=True, exist_ok=True)
            for script in scripts:
                (code_dir / script.filename).write_bytes(script.data)
        elif code_dir.is_dir() and not any(code_dir.iterdir()):
            code_dir.rmdir()
        if listings:
            driver_path.write_text(render_reproduce_driver(listings, spec_id), encoding="utf-8")
        elif previous_driver and written_by_sci_adk(previous_driver):
            driver_path.unlink()

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
