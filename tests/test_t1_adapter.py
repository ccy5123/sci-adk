"""
T-1 capability adapter + end-to-end autonomous verdict -- RED-first.

Pins the agreed seam (design/rigor-shell-architecture.md §3.3, F4):
  - The T-1 experiment capability lives in ``sci_adk/adapter/`` and provides a
    concrete ``ExperimentFn`` (signature unchanged: (Spec, Path) -> [EvidenceItem]).
  - The kernel (``compiler.py``) no longer holds the T-1 helper, and the kernel
    package never imports the adapter (one-way: adapter -> kernel).
  - Agents propose, the engine judges: the experiment emits Evidence carrying
    ``collision_count``; the binding verdict is rendered by the DecisionEngine
    applying the frozen numeric DecisionRule -- NO judge injected, fully autonomous.

The experiment fn is Docker-backed in production but here we inject a non-Docker
``executor`` (a thin seam) so the autonomous verdict is unit-tested without Docker
-- the *science* (encoding + verifier) is real, only the container is stubbed.
"""

from __future__ import annotations

import importlib
import json
import shutil
from datetime import datetime, timezone

import pytest

docker_required = pytest.mark.skipif(
    shutil.which("docker") is None, reason="docker CLI not available"
)

from sci_adk.core.claim import ClaimStatus, ConfidenceType
from sci_adk.core.evidence import BearingDirection, EvidenceKind
from sci_adk.core.spec import (
    DecisionRule,
    DecisionRuleKind,
    Hypothesis,
    HypothesisMode,
    MethodPlan,
    RawProposal,
    Spec,
    TargetClaim,
)
from sci_adk.loop.compiler import ResearchCompiler

from sci_adk.adapter.t1_capability import (
    T1_CAPABILITY_ID,
    build_t1_spec,
    t1_experiment,
)
from sci_adk.adapter.t1_encoding import Molecule


_SPEC_ID = "t1-real"
_HYP = "hyp-t1"


class _PureExecutor:
    """A non-Docker executor seam: runs the encoding script's numeric core in-process.

    The T-1 experiment fn delegates container execution to an injected executor
    exposing ``run_t1(molecules_payload) -> stats dict``. In production this is the
    Docker-backed implementation; here it computes the SAME statistics directly via
    the real verifier, so the science is genuine but no container is required.
    """

    image_name = "pure-inproc"

    def __init__(self) -> None:
        self.calls: list = []

    def run_t1(self, molecules: list[Molecule]) -> dict:
        from sci_adk.adapter.t1_encoding import verify_injectivity

        self.calls.append(list(molecules))
        stats = verify_injectivity(list(molecules))
        return {
            "success": True,
            "stats": stats,
            "provenance": {
                "image_name": self.image_name,
                "image_id": "inproc-0000",
                "commit_hash": "deadbeef",
            },
        }


def _clean_set() -> list[Molecule]:
    return [
        Molecule(atoms=["O", "H", "H"], bonds=[(0, 1, 1), (0, 2, 1)]),     # H2O
        Molecule(atoms=["C", "O", "O"], bonds=[(0, 1, 2), (0, 2, 2)]),     # CO2
        Molecule(atoms=["C", "H", "H", "H", "H"],
                 bonds=[(0, 1, 1), (0, 2, 1), (0, 3, 1), (0, 4, 1)]),       # CH4
        Molecule(atoms=["C", "N", "H"], bonds=[(0, 1, 3), (0, 2, 1)]),     # HCN
    ]


def _t1_spec() -> Spec:
    """The real T-1 Spec (delegates to the adapter's canonical builder).

    The rule statistic is what the experiment emits (collision_count -> Result.point),
    so the engine evaluates it AUTONOMOUSLY (design §4.2). mode=exploratory because a
    zero count is support for injectivity on the TESTED SET, not a universal proof (C6).
    """
    return build_t1_spec(spec_id=_SPEC_ID)


class TestAdapterExperimentFn:
    def test_capability_id_is_stable(self):
        assert isinstance(T1_CAPABILITY_ID, str) and T1_CAPABILITY_ID

    def test_experiment_fn_emits_collision_count_evidence(self, tmp_path):
        fn = t1_experiment(_clean_set(), executor=_PureExecutor())
        spec = _t1_spec()
        evidence = fn(spec, tmp_path)

        assert len(evidence) == 1
        ev = evidence[0]
        assert ev.kind == EvidenceKind.EXPERIMENT_RUN
        # The statistic the DecisionRule reads (collision_count) lands in Result.point.
        assert ev.result.point == 0.0
        # round_trip_ok + raw count preserved as a finding (audit), provenance present.
        assert "round_trip_ok" in (ev.result.finding or "")
        assert ev.provenance.environment and "pure-inproc" in ev.provenance.environment
        # Bearing targets the hypothesis (so ClaimUpdater pre-filters it correctly).
        assert any(b.target_id == _HYP for b in ev.bears_on)

    def test_collision_makes_point_positive(self, tmp_path):
        # Two isomorphic graphs => 1 collision => Result.point == 1.0 (=> refute later).
        iso_a = Molecule(atoms=["O", "H", "H"], bonds=[(0, 1, 1), (0, 2, 1)])
        iso_b = Molecule(atoms=["H", "H", "O"], bonds=[(0, 2, 1), (1, 2, 1)])
        fn = t1_experiment([iso_a, iso_b], executor=_PureExecutor())
        ev = fn(_t1_spec(), tmp_path)[0]
        assert ev.result.point == 1.0


class TestAutonomousVerdict:
    """compile(...) with NO judge yields a SUPPORTED/REFUTED Claim autonomously."""

    def test_clean_set_yields_supported_claim_no_judge(self, tmp_path):
        compiler = ResearchCompiler(workspace_dir=tmp_path)  # judge=None (autonomous)
        result = compiler.compile(
            "",  # proposal_text ignored when a pre-built spec is supplied
            spec=build_t1_spec(spec_id=_SPEC_ID),
            experiment=t1_experiment(_clean_set(), executor=_PureExecutor()),
        )

        # No agent checkpoint: the numeric threshold rule resolves autonomously.
        assert result.needs_agent is False
        assert len(result.claims) == 1
        claim = result.claims[0]
        assert claim.status == ClaimStatus.SUPPORTED
        # The verdict came from the engine's threshold handler (credence basis quotes
        # the rule), NOT from a judge and NOT from a bearing vote-count.
        assert claim.confidence.type == ConfidenceType.CREDENCE
        assert "threshold rule" in claim.confidence.basis
        # Honest scoping: the claim is exploratory (tested-set support, not a proof).
        assert claim.mode == HypothesisMode.EXPLORATORY

    def test_colliding_set_yields_refuted_claim_no_judge(self, tmp_path):
        iso_a = Molecule(atoms=["O", "H", "H"], bonds=[(0, 1, 1), (0, 2, 1)])
        iso_b = Molecule(atoms=["H", "H", "O"], bonds=[(0, 2, 1), (1, 2, 1)])
        compiler = ResearchCompiler(workspace_dir=tmp_path)
        result = compiler.compile(
            "",
            spec=build_t1_spec(spec_id=_SPEC_ID),
            experiment=t1_experiment([iso_a, iso_b], executor=_PureExecutor()),
        )
        assert result.needs_agent is False
        claim = result.claims[0]
        assert claim.status == ClaimStatus.REFUTED
        assert "threshold rule" in claim.confidence.basis

    def test_evidence_persisted_with_collision_count(self, tmp_path):
        compiler = ResearchCompiler(workspace_dir=tmp_path)
        result = compiler.compile(
            "",
            spec=build_t1_spec(spec_id=_SPEC_ID),
            experiment=t1_experiment(_clean_set(), executor=_PureExecutor()),
        )
        run_dir = tmp_path / "runs" / _SPEC_ID
        ev_files = list((run_dir / "evidence").glob("*.json"))
        assert len(ev_files) == 1
        on_disk = json.loads(ev_files[0].read_text(encoding="utf-8"))
        assert on_disk["result"]["point"] == 0.0


class TestSeamIsOneWay:
    """The kernel must not import the adapter (design §2.4 / F4). Convention-checked."""

    KERNEL_MODULES = [
        "sci_adk.loop.compiler",
        "sci_adk.loop.decision_engine",
        "sci_adk.loop.claim_updater",
        "sci_adk.loop.judge",
        "sci_adk.core.spec",
        "sci_adk.core.evidence",
        "sci_adk.core.claim",
        "sci_adk.core.parser",
        "sci_adk.render.paper",
    ]

    def test_no_kernel_module_imports_adapter(self):
        import ast
        import sci_adk

        offenders = []
        for modname in self.KERNEL_MODULES:
            mod = importlib.import_module(modname)
            src_file = mod.__file__
            tree = ast.parse(open(src_file, encoding="utf-8").read())
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name.startswith("sci_adk.adapter"):
                            offenders.append((modname, alias.name))
                elif isinstance(node, ast.ImportFrom):
                    if (node.module or "").startswith("sci_adk.adapter"):
                        offenders.append((modname, node.module))
        assert offenders == [], f"kernel modules import the adapter: {offenders}"


@docker_required
class TestDockerBackedProduction:
    """The PRODUCTION path: the real encoding runs inside sci-adk-python-base and the
    DecisionEngine renders an autonomous verdict (proves the science is Docker-backed,
    not only unit-tested)."""

    def test_t1_demo_set_supported_via_real_container(self, tmp_path):
        from sci_adk.adapter.t1_capability import (
            build_t1_demo_molecules,
            build_t1_spec,
            t1_experiment,
        )

        # Default executor => T1DockerExecutor => runs verify_injectivity in-container.
        compiler = ResearchCompiler(workspace_dir=tmp_path)
        result = compiler.compile(
            "",
            spec=build_t1_spec(spec_id=_SPEC_ID),
            experiment=t1_experiment(build_t1_demo_molecules()),
        )

        assert result.needs_agent is False
        claim = result.claims[0]
        assert claim.status == ClaimStatus.SUPPORTED
        assert "threshold rule" in claim.confidence.basis

        # Evidence provenance proves the container ran (image id captured).
        ev = result.evidence[0]
        assert ev.result.point == 0.0
        assert "docker" in (ev.provenance.environment or "").lower()
        assert "round_trip_ok" in (ev.result.finding or "")
