"""
T-1 capability: the adapter-served ``ExperimentFn`` for the molecular Gödel encoding.

This is the FIRST registered capability behind the kernel/adapter seam
(design/rigor-shell-architecture.md §3.3, F4): it replaces the milestone-1 toy that
lived in ``sci_adk.loop.compiler`` (``t1_molecular_experiment``). The kernel keeps
only the ``ExperimentFn`` *type* (``compiler.py``); this module provides a concrete
instance and never the reverse (adapter -> kernel only).

Contract honored:
  - ``ExperimentFn`` signature is unchanged: ``(Spec, Path) -> Sequence[EvidenceItem]``.
  - Agents propose, the engine judges: the experiment only PRODUCES Evidence
    carrying ``collision_count`` (-> ``Result.point``); the binding verdict is the
    DecisionEngine's, applying the frozen numeric ``DecisionRule`` autonomously.
  - No hardcoded metric here: the injectivity threshold is in the Spec's
    ``DecisionRule.params`` (built by ``build_t1_spec``), never a constant in code.

Execution seam (design §3.1, §6.2): the encoding+verifier is pure Python, so it runs
inside the ``sci-adk-python-base`` Docker image in production AND directly in unit
tests. The experiment fn delegates container work to an injected ``executor`` with a
``run_t1(molecules) -> dict`` method; the default is the Docker-backed executor, and
tests inject an in-process one. The *science* is never faked -- only the container is
a seam.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, List, Optional, Protocol, Sequence

from sci_adk.core.evidence import (
    Bearing,
    BearingDirection,
    EvidenceItem,
    EvidenceKind,
    Provenance,
    Result,
)
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

from sci_adk.adapter.t1_encoding import Molecule, verify_injectivity

# The capability id this plugin registers under (design §3.2). A runtime selector
# (CLI/adapter default) resolves to it; it is HOW, not WHAT, so it is NOT a frozen
# Spec field (F3) -- it travels only in Evidence provenance.
T1_CAPABILITY_ID = "t1-molecular-godel"

# Canonical T-1 identifiers (used by build_t1_spec and the experiment bearing).
_T1_HYP_ID = "hyp-t1"
_T1_DEFAULT_SPEC_ID = "t1-godel"

# The Spec's DecisionRule reads the statistic from ``Result.point`` (the engine's
# threshold handler is hardwired to the ``point`` field). The experiment therefore
# writes ``collision_count`` into ``Result.point`` and keeps the human-readable
# statistic name in the rule expression + params for the audit trail.
_POINT_FIELD = "point"


class T1Executor(Protocol):
    """The execution seam the T-1 experiment fn depends on.

    ``run_t1`` runs the encoding+verifier over ``molecules`` and returns:
        {"success": bool, "stats": <verify_injectivity dict>, "provenance": {...}}
    Production: a Docker-backed implementation. Tests: an in-process one. Either
    way the statistics come from the real ``verify_injectivity`` -- the seam isolates
    the container, not the science.
    """

    image_name: str

    def run_t1(self, molecules: List[Molecule]) -> dict:
        ...


def t1_experiment(
    molecules: Sequence[Molecule],
    executor: Optional["T1Executor"] = None,
) -> Callable[[Spec, Path], List[EvidenceItem]]:
    """Build the T-1 ``ExperimentFn`` over a designed ``molecules`` test set.

    Returns ``fn(spec, workspace_dir) -> [EvidenceItem]`` so the compiler stays
    domain-agnostic. The single EvidenceItem carries the verifier's
    ``collision_count`` in ``Result.point`` (the statistic the DecisionRule judges)
    and the full stats (``round_trip_ok``, raw count, codes) as a JSON finding for
    the audit record. Provenance records the capability + container (E3).

    Args:
        molecules: the explicit-graph test set to encode and verify.
        executor: the execution seam (default: Docker-backed ``T1DockerExecutor``).
    """
    # @MX:ANCHOR: [AUTO] the T-1 capability's ExperimentFn provider -- the adapter
    #   side of the kernel's Experiment interface (Spec -> Evidence). It only emits
    #   Evidence (collision_count -> Result.point); it never renders the verdict.
    # @MX:REASON: [AUTO] cli (--t1-demo), the autonomous-verdict tests, and the Docker
    #   production test all wire experiments through this factory; the engine judges
    #   the Evidence it produces. Breaking the (Spec,Path)->[EvidenceItem] contract or
    #   letting it self-certify a Claim would violate the agreed "agents propose, the
    #   engine judges" seam (design/rigor-shell-architecture.md §1).
    mols = list(molecules)
    exec_ = executor if executor is not None else T1DockerExecutor()

    def _run(spec: Spec, workspace_dir: Path) -> List[EvidenceItem]:
        outcome = exec_.run_t1(mols)
        stats = outcome["stats"]
        prov = outcome.get("provenance", {})

        collision_count = float(stats["collision_count"])
        # The statistic the engine reads (Result.point); the rest is audit detail.
        result = Result(
            type="quantitative",
            point=collision_count,
            finding=json.dumps(
                {
                    "statistic": "collision_count",
                    "collision_count": stats["collision_count"],
                    "round_trip_ok": stats["round_trip_ok"],
                    "n_molecules": stats["n_molecules"],
                    "capability": T1_CAPABILITY_ID,
                },
                ensure_ascii=False,
            ),
        )

        # data_source='generated': the molecule set is an in-silico GENUINE instance of
        # the formal referent (the encoding map), not a synthetic proxy for an external
        # phenomenon. The evidence-validity gate ALLOWS generated Evidence on a formal
        # hypothesis (design/evidence-validity.md §1, Guard 3 item 3) -- T-1 is the
        # legitimate computational result.

        # collision_count == 0 points toward SUPPORTS; > 0 toward REFUTES. This
        # bearing is the experiment's HONEST read of its own statistic; the binding
        # verdict still comes from the engine applying the frozen rule.
        direction = (
            BearingDirection.SUPPORTS
            if stats["collision_count"] == 0
            else BearingDirection.REFUTES
        )
        target_id = spec.hypotheses[0].id if spec.hypotheses else _T1_HYP_ID

        evidence = EvidenceItem(
            id=_evidence_id(),
            created_at=datetime.now(timezone.utc),
            spec_id=spec.id,
            kind=EvidenceKind.EXPERIMENT_RUN,
            provenance=Provenance(
                code_ref=prov.get("commit_hash"),
                environment=_environment(prov),
                data_source="generated",
            ),
            result=result,
            bears_on=[Bearing(target_id=target_id, direction=direction)],
        )
        _save_evidence(evidence, spec, workspace_dir)
        return [evidence]

    return _run


def build_t1_demo_molecules() -> List[Molecule]:
    """The built-in designed T-1 test set (real graphs, chosen to stress injectivity).

    Includes H2O, CO2, CH4 (the canonical trio) plus HCN, H2O2, and formaldehyde --
    molecules that share atom multisets or bonding patterns the toy encoding would
    collide on, so a zero collision count is a meaningful result, not a triviality.
    """
    return [
        Molecule(atoms=["O", "H", "H"], bonds=[(0, 1, 1), (0, 2, 1)]),            # H2O
        Molecule(atoms=["C", "O", "O"], bonds=[(0, 1, 2), (0, 2, 2)]),            # CO2 (O=C=O)
        Molecule(atoms=["C", "H", "H", "H", "H"],
                 bonds=[(0, 1, 1), (0, 2, 1), (0, 3, 1), (0, 4, 1)]),              # CH4
        Molecule(atoms=["C", "N", "H"], bonds=[(0, 1, 3), (0, 2, 1)]),            # HCN (H-C#N)
        Molecule(atoms=["O", "O", "H", "H"],
                 bonds=[(0, 1, 1), (0, 2, 1), (1, 3, 1)]),                         # H2O2 (H-O-O-H)
        Molecule(atoms=["C", "O", "H", "H"],
                 bonds=[(0, 1, 2), (0, 2, 1), (0, 3, 1)]),                         # H2C=O
    ]


def build_t1_spec(spec_id: str = _T1_DEFAULT_SPEC_ID) -> Spec:
    """Build the real T-1 ``Spec`` carrying the numeric injectivity ``DecisionRule``.

    The rule is ``threshold``: ``collision_count == 0`` over the test set => support
    (injective on the tested set); ``> 0`` => refute. Its threshold lives in
    ``params`` (no hardcoded metric, D1). The statistic name is recorded for the
    audit; the engine reads the value from ``Result.point``.

    The hypothesis is ``exploratory`` (honest scoping, C6): a zero collision count is
    empirical support for injectivity ON THE TESTED SET, not a universal proof of
    bijectivity (that would be a ``proof`` rule, out of scope here).

    Evidence-validity (design/evidence-validity.md §1): the referent is ``formal`` --
    injectivity over the GENERATED molecule set IS the claim's referent (the encoding
    map), so the generated Evidence is a genuine computational result, not a synthetic
    proxy for an external phenomenon. It carries a non-circularity attestation: the
    generator emits molecular graphs with no guarantee of distinct codes, and the
    verifier independently checks for collisions -- so a zero count is informative, not
    a tautology.
    """
    rule = DecisionRule(
        kind=DecisionRuleKind.THRESHOLD,
        expression=(
            "collision_count == 0 over the test set => support (injective on the "
            "tested set); collision_count > 0 => refute"
        ),
        # ``statistic`` documents which measurement this judges (the engine reads the
        # value from Result.point); ``op``/``value`` are the machine-usable threshold.
        params={"statistic": "collision_count", "op": "==", "value": 0.0},
    )
    return Spec(
        id=spec_id,
        version=1,
        raw_proposal=RawProposal(
            background=(
                "Molecular graphs can be serialized to integers. A Gödel-style "
                "prime encoding promises an injective, recoverable mapping."
            ),
            goal=(
                "Demonstrate an injective Gödel-style encoding of molecular graphs "
                "on a designed test set (unique integer per non-isomorphic molecule)."
            ),
            method=(
                "Canonically label each graph (Morgan-style refinement), encode atoms "
                "and bonds as prime-power products packed into one integer, and verify "
                "zero collisions plus exact round-trip decode over the test set."
            ),
            expected_output=(
                "A unique integer per non-isomorphic molecule and a decode that "
                "recovers the canonical graph (injectivity on the tested sample)."
            ),
        ),
        hypotheses=[
            Hypothesis(
                id=_T1_HYP_ID,
                statement=(
                    "Molecule graphs admit an injective Gödel-style encoding on the "
                    "tested set"
                ),
                mode=HypothesisMode.EXPLORATORY,
                decision_rule=rule,
                referent="formal",
                non_circularity=(
                    "the generator emits molecular graphs with no guarantee of distinct "
                    "codes, so collisions could occur; the verifier independently checks "
                    "the encoding for collisions over the generated set -- a zero count "
                    "is therefore informative, not a property baked into the generator"
                ),
            )
        ],
        method=MethodPlan(approaches=["prime-Gödel graph encoding"], tools=[]),
        target_claims=[
            TargetClaim(
                id="tc-t1",
                statement="An injective encoding exists on the tested set",
                answers=_T1_HYP_ID,
            )
        ],
    )


# ---------------------------------------------------------------------------
# Docker-backed executor (production path). Runs the SAME pure verifier inside the
# sci-adk-python-base image so the result is reproducible and provenance-stamped.
# ---------------------------------------------------------------------------

class T1DockerExecutor:
    """Run the T-1 encoding+verifier inside the ``sci-adk-python-base`` container.

    The encoding module is pure Python; this executor ships the molecule set as JSON
    and runs ``sci_adk.adapter.t1_encoding.verify_injectivity`` in the container,
    parsing back the stats. Provenance (image id, git commit) is captured by the
    underlying ``DockerExecutor``.
    """

    image_name = "sci-adk-python-base"

    def __init__(self, workspace_dir: Optional[Path] = None) -> None:
        self.workspace_dir = workspace_dir or Path.cwd()

    def run_t1(self, molecules: List[Molecule]) -> dict:
        # Imported lazily so importing this module never requires Docker.
        from sci_adk.runner.docker_executor import DockerExecutor

        payload = json.dumps(
            [{"atoms": m.atoms, "bonds": [list(b) for b in m.bonds]} for m in molecules]
        )
        script = _T1_CONTAINER_SCRIPT
        executor = DockerExecutor(
            image_name=self.image_name, workspace_dir=self.workspace_dir
        )
        # The container needs sci_adk importable: the workspace mount includes src/.
        run = executor.execute_python(script, script_args=[payload])
        stats: dict = {}
        if run["success"] and run["stdout"]:
            try:
                stats = json.loads(run["stdout"].strip().splitlines()[-1])
            except (json.JSONDecodeError, IndexError):
                stats = {}
        if not stats:
            raise RuntimeError(
                "T-1 container run produced no parseable stats; "
                f"stderr={run.get('stderr')!r}"
            )
        return {"success": run["success"], "stats": stats, "provenance": run["provenance"]}


# The script executed inside the container. It reconstructs Molecules from the JSON
# payload and runs the real verifier, printing the stats JSON on the last stdout line.
_T1_CONTAINER_SCRIPT = """
import sys, json
sys.path.insert(0, "/workspace/src")
from sci_adk.adapter.t1_encoding import Molecule, verify_injectivity

payload = json.loads(sys.argv[1])
mols = [Molecule(atoms=m["atoms"], bonds=[tuple(b) for b in m["bonds"]]) for m in payload]
stats = verify_injectivity(mols)
print(json.dumps(stats))
"""


# ---------------------------------------------------------------------------
# Evidence helpers (kept local to the adapter -- the kernel writes its own records).
# ---------------------------------------------------------------------------

def _evidence_id() -> str:
    import uuid

    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"evi-t1-{ts}-{uuid.uuid4().hex[:8]}"


def _environment(prov: dict) -> str:
    return (
        f"capability:{T1_CAPABILITY_ID}, "
        f"docker:{prov.get('image_name', 'unknown')}, "
        f"image_id:{prov.get('image_id', 'unknown')}"
    )


def _save_evidence(evidence: EvidenceItem, spec: Spec, workspace_dir: Path) -> None:
    evidence_dir = Path(workspace_dir) / "runs" / spec.id / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    (evidence_dir / f"{evidence.id}.json").write_text(
        json.dumps(evidence.model_dump(mode="json"), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


__all__ = [
    "T1_CAPABILITY_ID",
    "T1Executor",
    "T1DockerExecutor",
    "t1_experiment",
    "build_t1_spec",
    "build_t1_demo_molecules",
]
