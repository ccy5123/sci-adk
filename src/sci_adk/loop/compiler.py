"""
ResearchCompiler -- the deterministic orchestrator (the research compiler core).

Drives a four-pane proposal through the parts that need NO LLM (zero cost):

    proposal text
        -> parse (ProposalParser)            -> Spec        (runs/<id>/spec.json)
        -> [experiment hook]                 -> Evidence    (runs/<id>/evidence/)
        -> ClaimUpdater + DecisionEngine     -> Claims      (runs/<id>/claims/)
        -> render_paper                      -> draft       (runs/<id>/paper/draft.md)

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

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional, Sequence

from sci_adk.core.claim import Claim
from sci_adk.core.evidence import EvidenceItem
from sci_adk.core.parser import ProposalParser
from sci_adk.core.spec import DecisionRuleKind, Spec
from sci_adk.loop.claim_updater import ClaimUpdater
from sci_adk.loop.judge import Judge
from sci_adk.loop.verdict import CheckpointModel
from sci_adk.render.paper import render_paper

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

        Returns:
            A ``CompileResult`` (inspect ``needs_agent`` / ``checkpoints``).
        """
        spec = spec if spec is not None else ProposalParser().parse(
            proposal_text, spec_id=spec_id
        )
        run_dir = self.workspace_dir / "runs" / spec.id
        run_dir.mkdir(parents=True, exist_ok=True)
        self._save_spec(spec, run_dir)

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

        paper = render_paper(
            spec, claims, evidence,
            pending=[c.__dict__ for c in checkpoints],
        )
        paper_path = run_dir / "paper" / "draft.md"
        paper_path.parent.mkdir(parents=True, exist_ok=True)
        paper_path.write_text(paper, encoding="utf-8")

        if checkpoints:
            self._save_checkpoints(checkpoints, run_dir)

        return CompileResult(
            spec=spec,
            evidence=evidence,
            claims=claims,
            checkpoints=checkpoints,
            run_dir=run_dir,
            paper_path=paper_path,
        )

    # -- helpers -----------------------------------------------------------

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
