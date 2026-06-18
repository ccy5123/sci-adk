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
from sci_adk.loop.claim_updater import ClaimUpdater
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
    FigureConsistencyReport,
    FigureSpec,
    check_figure_consistency,
    figure_labels,
)
from sci_adk.render.paper import render_paper_latex
from sci_adk.render.prose import PaperProse
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
    ) -> None:
        self.workspace_dir = Path(workspace_dir) if workspace_dir else Path.cwd()
        self.judge = judge

    def compile(
        self,
        proposal_text: str,
        *,
        spec_id: Optional[str] = None,
        spec: Optional[Spec] = None,
        experiment: Optional[ExperimentFn] = None,
        prose: Optional[PaperProse] = None,
        figures: Optional[Sequence[FigureSpec]] = None,
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
            figures: optional agent-authored ``FigureSpec`` list
                (design/paper-figures-and-si.md, Phase 1). Threaded into the LaTeX
                renderer (pgfplots-native, the y pulled from this run's Evidence). Never
                LLM-generated -- input, the same spirit as ``prose``. After rendering,
                a NON-BLOCKING ``check_figure_consistency`` over the rendered body is
                surfaced in ``CompileResult.figure_consistency`` (a report, not a gate;
                the hard verify-gate is Phase 3). Absent -> no figures.

        Returns:
            A ``CompileResult`` (inspect ``needs_agent`` / ``checkpoints``).
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
        pw_checkpoint = prior_work_checkpoint(spec)
        self._save_prior_work_checkpoint(pw_checkpoint, run_dir)

        evidence: List[EvidenceItem] = []
        if experiment is not None:
            produced = experiment(spec, self.workspace_dir)
            evidence = list(produced) if produced else []

        claims: List[Claim] = []
        if evidence:
            claims = ClaimUpdater(
                spec, self.workspace_dir, judge=self.judge
            ).update_claims_from_evidence(evidence)

        checkpoints = self._collect_checkpoints(spec, evidence)

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
        # in-memory ``evidence`` the claim was derived from (NOT disk) so the message and
        # the claim status agree even in this single pass.
        novelty_checkpoints = self._collect_novelty_checkpoints(spec, claims, evidence)

        # Citations + bibliography are gathered for the run (renderers stay pure --
        # data in, string out; the compiler is the composition root that locates them).
        pending_dicts = [c.__dict__ for c in checkpoints]
        cited_dois = self._gather_cited_dois(evidence, run_dir)

        paper_dir = run_dir / "paper"
        paper_dir.mkdir(parents=True, exist_ok=True)

        # Co-locate references.bib next to draft.tex so the paper/ folder is
        # self-contained on Overleaf (upload-as-is resolves \bibliography{references}).
        # The compiler does the copy (the renderer stays pure); it then passes the
        # CO-LOCATED path, whose stem is "references", to the renderer.
        bib_path = self._colocate_bib(run_dir, paper_dir)

        # The .tex is THE paper artifact (Overleaf default pdflatex). Deterministic and
        # offline -- no LLM, no network (render_paper_latex is pure). The Markdown
        # render_paper remains a library function but is no longer auto-emitted.
        figures = list(figures or [])
        paper_tex = render_paper_latex(
            spec, claims, evidence,
            pending=pending_dicts,
            prose=prose,
            cited_dois=cited_dois,
            bib_path=bib_path,
            figures=figures,
        )
        paper_path = paper_dir / "draft.tex"
        paper_path.write_text(paper_tex, encoding="utf-8")

        # Supporting Information (design/paper-figures-and-si.md Phase 2 / D3): a
        # STANDALONE si.tex = the deterministic record dump (every Evidence item, the
        # numeric data tables, ALL figures, the verdicts + frozen decision rules). It
        # uploads alongside draft.tex as a second compilable document in paper/.
        #
        # digest=None on purpose: at COMPILE time the evidence is NOT yet persisted to
        # disk (the loop persists AFTER compile), so record_digest(run_dir) here would
        # digest an INCOMPLETE run dir. So Phase 2 does NOT embed the digest -- the SI's
        # integrity section points to `sci-adk verify` (which recomputes the digest over
        # the persisted run). Embedding the real digest at render time is a later
        # refinement. (Cross-DOCUMENT main<->SI \ref -- e.g. "Fig. S2" in the main paper
        # resolving into the SI -- is deferred to Phase 3: separate compiles would need
        # the `xr` package + a compile-order dependency; the SI is INTERNALLY consistent
        # here via figure_labels' unique-id enforcement.)
        si_tex = render_si_latex(
            spec, claims, evidence, figures=figures, digest=None
        )
        si_path = paper_dir / "si.tex"
        si_path.write_text(si_tex, encoding="utf-8")

        # Prose<->figure ref consistency (design/paper-figures-and-si.md D4): scan the
        # RENDERED body for \ref{fig:...}/\label integrity. NON-BLOCKING -- surfaced in
        # the result (a warning channel, like the contested/novelty checkpoints), never
        # a hard fail (the verify-style gate is Phase 3). figure_labels enforces unique
        # ids; rendering above would already have raised on a missing evidence id.
        figure_consistency = check_figure_consistency(
            figure_labels(figures), paper_tex
        )

        if checkpoints:
            self._save_checkpoints(checkpoints, run_dir)

        return CompileResult(
            spec=spec,
            evidence=evidence,
            claims=claims,
            checkpoints=checkpoints,
            run_dir=run_dir,
            paper_path=paper_path,
            si_path=si_path,
            prior_work_checkpoint=pw_checkpoint,
            contested_checkpoints=contested_checkpoints,
            novelty_checkpoints=novelty_checkpoints,
            figure_consistency=figure_consistency,
        )

    # -- helpers -----------------------------------------------------------

    @staticmethod
    def _gather_cited_dois(
        evidence: Sequence[EvidenceItem], run_dir: Path
    ) -> List[str]:
        """Collect the DOIs to cite for this run, de-duplicated, first-seen order.

        Two sources (a cited DOI is cited regardless of whether its PDF downloaded):
          (a) ``LITERATURE`` EvidenceItems -- their ``result.finding`` is the JSON
              summary the acquirer writes (``acquired[].doi`` + ``failed[].doi``);
          (b) the run's ``artifacts/literature/manifest.csv`` (the t1-godel shape,
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
        """Surface a reason-tailored novelty checkpoint per novelty=True hypothesis whose
        ``claim-novelty-<hyp>`` is PROPOSED (NON-HALT; ``novelty_open`` keys on the
        novelty claim just persisted, so a re-compile after a found_nothing decision --
        which makes the claim SUPPORTED -- surfaces nothing).

        Iterates the SPEC hypotheses (not ``claims``): a novelty hypothesis is open even
        with no experiment claim, exactly as the novelty pass in ClaimUpdater persists
        its novelty claim independently of experiment evidence.

        The reason is derived from the SAME in-memory ``evidence`` the novelty claim was
        derived from (``novelty_reason_from_decisions`` over the NOVELTY_DECISIONs in
        ``evidence``), NOT from disk: in a single-pass ``compile()`` an in-memory
        found_something decision is not yet persisted, so a disk read would emit the wrong
        (not_searched / "go search") prompt. ``novelty_open`` reads the just-persisted
        novelty CLAIM status, which IS on disk -- that read is correct.
        """
        novelty_decisions = [
            ev for ev in evidence if ev.kind == EvidenceKind.NOVELTY_DECISION
        ]
        out: List[NoveltyCheckpoint] = []
        for h in spec.hypotheses:
            if not h.novelty:
                continue
            if novelty_open(spec, h.id, self.workspace_dir):
                reason = novelty_reason_from_decisions(h.id, novelty_decisions)
                out.append(
                    novelty_checkpoint(spec, h.id, spec.version, reason=reason)
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
