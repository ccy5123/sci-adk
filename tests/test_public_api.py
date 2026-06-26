"""1.0 public-API contract guard (G-D D1).

``sci_adk`` promises a curated, stable Python API under semver 1.0. The exact
surface is fixed in ``design/surface-freeze-analysis.md`` §4. This test makes the
promise enforceable: the re-export set is pinned, every promised name imports,
each resolves to the kernel module it should, and the internal ``adapter`` (A1b,
scoped out of the 1.0 claim — ``design/g-a-a3-decision.md``) is NOT exposed.

If you change ``sci_adk.__all__``, this test fails on purpose — a stability
promise may only move by a deliberate edit here (a removal/rename is a breaking
change that needs a major bump; an addition is additive 1.x growth).
"""

from __future__ import annotations

import importlib

import sci_adk

# The frozen 1.0 curated surface (design/surface-freeze-analysis.md §4).
EXPECTED_PUBLIC_API = frozenset(
    {
        # Spec — the frozen compiler input (record)
        "Spec",
        "Hypothesis",
        "RawProposal",
        "MethodPlan",
        "DecisionRule",
        "TargetClaim",
        "DiscriminatingCase",
        "HypothesisMode",
        "DecisionRuleKind",
        # Evidence — the append-only record
        "EvidenceItem",
        "Provenance",
        "Result",
        "Bearing",
        "Cost",
        "EvidenceKind",
        "BearingDirection",
        # Claim — the revisable belief
        "Claim",
        "Confidence",
        "EvidenceLink",
        "StatusChange",
        "ClaimStatus",
        "ConfidenceType",
        "ConfidenceLevel",
        "EvidenceLinkRole",
        # the verdict engine + the sole read-only verdict path
        "DecisionEngine",
        "verify_run",
        "verify_package",
        "VerifyReport",
        "PackageVerifyReport",
    }
)


def test_all_matches_the_frozen_contract():
    """__all__ is EXACTLY the promised set — no silent drift in either direction."""
    assert set(sci_adk.__all__) == EXPECTED_PUBLIC_API


def test_all_has_no_duplicates():
    assert len(sci_adk.__all__) == len(set(sci_adk.__all__))


def test_every_public_name_is_importable():
    """Every promised name resolves on the package root (the re-export is wired)."""
    missing = [name for name in EXPECTED_PUBLIC_API if not hasattr(sci_adk, name)]
    assert missing == [], f"promised public names not importable from sci_adk: {missing}"


def test_star_import_exposes_exactly_the_contract():
    """`from sci_adk import *` binds exactly __all__ (no leakage of submodule names)."""
    ns: dict = {}
    exec("from sci_adk import *", ns)
    bound = {k for k in ns if not k.startswith("__")}
    assert bound == EXPECTED_PUBLIC_API


def test_public_names_resolve_to_kernel_modules():
    """Representative re-exports point at the right kernel module (correct wiring)."""
    expected_module = {
        "Spec": "sci_adk.core.spec",
        "Hypothesis": "sci_adk.core.spec",
        "EvidenceItem": "sci_adk.core.evidence",
        "Provenance": "sci_adk.core.evidence",
        "Claim": "sci_adk.core.claim",
        "ClaimStatus": "sci_adk.core.claim",
        "DecisionEngine": "sci_adk.loop.decision_engine",
        "verify_run": "sci_adk.loop.verify",
        "verify_package": "sci_adk.loop.verify",
        "VerifyReport": "sci_adk.loop.verify",
    }
    for name, module in expected_module.items():
        obj = getattr(sci_adk, name)
        assert obj.__module__ == module, f"{name}.__module__ = {obj.__module__}, want {module}"


def test_adapter_is_not_part_of_the_public_api():
    """The adapter (A1b, scoped out) is internal — never re-exported from the root."""
    for name in sci_adk.__all__:
        obj = getattr(sci_adk, name)
        mod = getattr(obj, "__module__", "")
        assert not mod.startswith("sci_adk.adapter"), (
            f"{name} resolves into sci_adk.adapter ({mod}) — the adapter is internal, "
            "not part of the 1.0 public API"
        )


def test_importing_root_does_not_pull_in_the_adapter():
    """Importing the public root must not transitively import the adapter package.

    The kernel/adapter seam is one-way (adapter -> kernel). A consumer doing
    `import sci_adk` for the curated kernel API must not drag the T-1 adapter in.
    """
    import sys

    # Re-import cleanly: drop any adapter modules a prior test may have loaded.
    for mod in [m for m in sys.modules if m.startswith("sci_adk.adapter")]:
        del sys.modules[mod]
    importlib.reload(sci_adk)
    assert not any(m.startswith("sci_adk.adapter") for m in sys.modules), (
        "importing sci_adk pulled in sci_adk.adapter — the curated root must stay "
        "kernel-only"
    )
