"""
LLM-judge interface for the DecisionEngine (design/decision-engine.md Decision 4).

The ``proof`` and ``qualitative`` decision-rule kinds do not reduce to a formula
(D8): the engine must *route* them to a judge, not fabricate a number. This
module defines the judge boundary the engine depends on -- a ``Judge`` Protocol
and the ``JudgeVerdict`` it returns -- so the engine stays pure and testable: a
``FakeJudge`` is injected in tests, the real Claude-backed judge in production.

Backend status (2026-06-16): the *interface* lands here; the live Claude-backed
adapter (``ClaudeJudge``) is deferred -- how sci-adk invokes Claude at runtime
(``claude -p`` headless vs API) is a separate infra decision, mirroring the
paperforge subprocess integration. ``ClaudeJudge`` is a placeholder that raises
so a caller never silently receives a fabricated verdict.

Override (design/decision-engine.md §0 + Decision 4): ``proof`` routes to the
judge too (not straight to a human), but the judge MUST attempt a counterexample
search, and a confident "verified" verdict still routes to a human spot-check
before a Claim can become ``supported`` -- the engine encodes that rail, not this
module. The judge only reports what it found.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol, Sequence, runtime_checkable

from sci_adk.core.claim import ConfidenceLevel
from sci_adk.core.evidence import BearingDirection
from sci_adk.loop.verdict import VerdictTrail


@dataclass(frozen=True)
class JudgeVerdict:
    """
    A judge's answer for one non-numeric rule.

    Attributes:
        direction: the judge's call (supports / refutes / neutral / inconclusive).
        level: confidence strength of that call. WEAK/NONE means "not confident
            enough to act" -- the engine escalates those to a human.
        basis: the judge's reasoning (becomes part of the Verdict basis, C3/D2).
        counterexample: proof-specific -- the judge found a counterexample
            (decisive refutation), regardless of ``direction``.
        trail: the chief-over-N provenance trail behind this verdict
            (``verdicts/<hyp-id>.json``). Additive (default None) so the Judge
            Protocol signatures are unchanged and existing callers stay
            backward-constructible. The engine's F2 gate accepts a BINDING
            (SUPPORTS/REFUTES) non-numeric verdict only when a well-formed trail is
            present (design/rigor-shell-architecture.md §2.3, F2).
    """

    direction: BearingDirection
    level: ConfidenceLevel
    basis: str
    counterexample: bool = False
    trail: Optional[VerdictTrail] = None


@runtime_checkable
class Judge(Protocol):
    """The judge boundary the DecisionEngine routes ``proof``/``qualitative`` to."""

    def judge_qualitative(
        self,
        criterion: str,
        finding: str,
        params: dict,
    ) -> JudgeVerdict:
        """Judge a finding against the rule's prose ``criterion`` (rule.expression).
        Applies the Spec's own standard -- never a global rubric (D1)."""
        ...

    def judge_proof(
        self,
        criterion: str,
        finding: str,
        artifact_ref: Optional[str],
        evidence_kinds: Sequence[str],
        params: dict,
    ) -> JudgeVerdict:
        """Judge a proof, ATTEMPTING a counterexample search (Decision 4 rail).
        Set ``counterexample=True`` when one is found (decisive refute)."""
        ...


class ClaudeJudge:
    """
    Live LLM-judge over the Claude backend -- DEFERRED (interface placeholder).

    The runtime invocation (``claude -p`` headless vs API vs GLM) is a separate
    infra decision and is intentionally not wired here (Decision 4 follow-up).
    Methods raise so a caller fails loudly rather than silently receiving a fake
    verdict; inject a real ``Judge`` implementation to enable proof/qualitative
    evaluation.
    """

    _MSG = (
        "ClaudeJudge backend is not wired yet (Decision 4 follow-up): the "
        "runtime Claude invocation is a separate infra decision. Inject a Judge "
        "implementation into DecisionEngine to evaluate proof/qualitative rules."
    )

    def judge_qualitative(self, criterion: str, finding: str, params: dict) -> JudgeVerdict:
        raise NotImplementedError(self._MSG)

    def judge_proof(
        self,
        criterion: str,
        finding: str,
        artifact_ref: Optional[str],
        evidence_kinds: Sequence[str],
        params: dict,
    ) -> JudgeVerdict:
        raise NotImplementedError(self._MSG)


__all__ = ["JudgeVerdict", "Judge", "ClaudeJudge"]
