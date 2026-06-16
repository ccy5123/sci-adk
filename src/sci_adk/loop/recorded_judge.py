"""
``RecordedJudge`` -- a deterministic ``Judge`` that reads agent-authored verdicts.

design/rigor-shell-architecture.md §5.2 (step 4): the turnkey loop re-enters by
injecting a ``RecordedJudge(run_dir)``. Its ``judge_qualitative`` / ``judge_proof``
read the chief verdict from ``verdicts/<hyp-id>.json``, deserialize a
:class:`VerdictTrail`, and return a :class:`JudgeVerdict` carrying the chief's
direction/level/basis/counterexample plus the loaded ``trail``. There is NO LLM and
NO network here -- it is pure JSON deserialization, which is why it lives in the
KERNEL (the adapter-side concern is only the agent's *act of authoring* the verdict
file with its chief-over-N reasoning, not the code that reads it; F2).

Seam constraint: the ``Judge`` Protocol signatures are fixed and do NOT include the
hypothesis id. A run holds one verdict file per hypothesis, each with
``rubric_expression == rule.expression``; ``RecordedJudge`` resolves the verdict for
the rule under evaluation by matching the ``criterion`` it is handed
(= ``rule.expression``) against a trail's ``rubric_expression``. An absent or
unmatched verdict -> an inconclusive-shaped verdict with NO trail, so the engine
refuses to bind and the checkpoint stays open (never a fabricated verdict, D8).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Optional, Sequence

from pydantic import ValidationError

from sci_adk.core.claim import ConfidenceLevel
from sci_adk.core.evidence import BearingDirection
from sci_adk.loop.judge import JudgeVerdict
from sci_adk.loop.verdict import VerdictTrail


class RecordedJudge:
    """A ``Judge`` that returns agent-authored verdicts from ``verdicts/*.json``.

    Deterministic and LLM-free. Construct with the run directory; the verdict files
    are read lazily and cached on first access.
    """

    def __init__(self, run_dir: Path) -> None:
        self._run_dir = Path(run_dir)
        self._by_hypothesis: Optional[Dict[str, VerdictTrail]] = None

    # -- Judge Protocol ----------------------------------------------------

    def judge_qualitative(
        self,
        criterion: str,
        finding: str,
        params: dict,
    ) -> JudgeVerdict:
        """Return the recorded chief verdict whose trail judged ``criterion``."""
        return self._verdict_for_criterion(criterion)

    def judge_proof(
        self,
        criterion: str,
        finding: str,
        artifact_ref: Optional[str],
        evidence_kinds: Sequence[str],
        params: dict,
    ) -> JudgeVerdict:
        """Return the recorded chief verdict whose trail judged ``criterion``."""
        return self._verdict_for_criterion(criterion)

    # -- direct lookup (loop/tests) ---------------------------------------

    def verdict_for(self, hypothesis_id: str) -> Optional[JudgeVerdict]:
        """The recorded verdict for ``hypothesis_id``, or ``None`` if none on disk."""
        trail = self._trails().get(hypothesis_id)
        return None if trail is None else self._to_verdict(trail)

    # -- internals ---------------------------------------------------------

    def _verdict_for_criterion(self, criterion: str) -> JudgeVerdict:
        # Known limitation of the criterion-match seam: because the Judge Protocol
        # signature carries ``criterion`` (= rule.expression) but NOT the hypothesis
        # id, two hypotheses that happen to share an IDENTICAL rule.expression are
        # indistinguishable here. The kernel cannot correctly attribute belief under
        # that ambiguity, so it REFUSES (raises) rather than silently first-matching
        # -- a mis-attributed belief is worse than a loud failure. (Distinct rule
        # expressions per hypothesis are the normal case and resolve cleanly.)
        matches = [
            trail for trail in self._trails().values()
            if trail.rubric_expression == criterion
        ]
        if len(matches) > 1:
            ids = ", ".join(sorted(t.hypothesis_id for t in matches))
            raise ValueError(
                f"ambiguous verdict match: hypotheses [{ids}] share the same "
                f"rule expression {criterion!r}; cannot attribute belief. Give the "
                f"hypotheses distinct DecisionRule.expression text."
            )
        if matches:
            return self._to_verdict(matches[0])
        return self._absent()

    def _trails(self) -> Dict[str, VerdictTrail]:
        if self._by_hypothesis is None:
            self._by_hypothesis = self._load_trails(self._run_dir / "verdicts")
        return self._by_hypothesis

    @staticmethod
    def _load_trails(verdicts_dir: Path) -> Dict[str, VerdictTrail]:
        """Load every ``verdicts/*.json`` into a trail, keyed by hypothesis id.

        A hand-authored verdict file may be truncated, contain a typo, or miss
        required fields. Rather than crash with a raw traceback (the file is human
        input), each file's parse + validate is wrapped and re-raised as a clear,
        file-naming ``ValueError`` so the CLI can report it legibly.
        """
        trails: Dict[str, VerdictTrail] = {}
        if not verdicts_dir.is_dir():
            return trails
        for path in sorted(verdicts_dir.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                trail = VerdictTrail.model_validate(data)
            except (json.JSONDecodeError, ValidationError) as e:
                raise ValueError(f"malformed verdict file {path}: {e}") from e
            trails[trail.hypothesis_id] = trail
        return trails

    @staticmethod
    def _to_verdict(trail: VerdictTrail) -> JudgeVerdict:
        chief = trail.chief
        return JudgeVerdict(
            direction=chief.direction,
            level=chief.level,
            basis=chief.basis,
            counterexample=chief.counterexample,
            trail=trail,
        )

    @staticmethod
    def _absent() -> JudgeVerdict:
        """An inconclusive verdict with NO trail -> the engine refuses to bind."""
        return JudgeVerdict(
            direction=BearingDirection.INCONCLUSIVE,
            level=ConfidenceLevel.NONE,
            basis="no recorded verdict on disk for this rule (verdicts/<hyp-id>.json "
            "absent or rubric mismatch); checkpoint stays open",
            counterexample=False,
            trail=None,
        )


__all__ = ["RecordedJudge"]
