"""
Capability registry -- the adapter-side selector for ``ExperimentFn`` providers.

design/rigor-shell-architecture.md §3.2 (F3): an arbitrary-domain proposal must select
and author its experiment WITHOUT the kernel knowing the domain. The mechanism is a
runtime selector (``--capability <id>`` / an adapter default) plus this adapter-side
registry mapping a ``capability id`` -> an ``ExperimentFn`` provider. A per-domain
plugin registers itself under its id; the compiler asks the adapter for the resolved
``ExperimentFn`` and runs it through the unchanged Interface B (compiler.py:121). The
kernel sees only ``experiment: ExperimentFn`` -- never this registry, the selector, or
the domain.

Capability is HOW, not WHAT (F3): it is resolved OUTSIDE the frozen Spec and travels
only in ``EvidenceItem.provenance`` (anti method-shopping, §3.2 step 4). T-1 is the
FIRST registered capability (§3.3): importing this module registers it under
``T1_CAPABILITY_ID``, wrapping ``t1_experiment`` / ``build_t1_spec`` /
``build_t1_demo_molecules``.

Seam direction (F4): this module lives in ``sci_adk.adapter`` and imports the kernel's
``ExperimentFn`` *type* + ``Spec`` *type* only -- ``adapter -> kernel`` is allowed. The
kernel never imports this module; the CLI (the composition root) does.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

from sci_adk.core.spec import Spec
from sci_adk.loop.compiler import ExperimentFn


# @MX:ANCHOR: [AUTO] the capability-selection contract behind the F3 runtime selector.
#   A CapabilityProvider is the adapter's typed carrier mapping a capability id to its
#   ExperimentFn factory (+ optional no-proposal demo support). The kernel never sees
#   this type -- it only receives the resolved ExperimentFn.
# @MX:REASON: [AUTO] the CLI (--capability / --t1-demo), the registry resolution, and
#   every per-domain plugin (T-1 first) construct/consume this; changing its shape or
#   letting it leak into the kernel would violate the agreed kernel/adapter seam
#   (design/rigor-shell-architecture.md §3.2/§3.3, F3/F4).
@dataclass(frozen=True)
class CapabilityProvider:
    """A registered capability: an id + how to produce its ``ExperimentFn``.

    Attributes:
        id: the capability id the runtime selector resolves (e.g. T1_CAPABILITY_ID).
        experiment_fn: ``(**options) -> ExperimentFn`` -- builds the (Spec, Path) ->
            [EvidenceItem] hook the compiler runs. Options are capability-specific
            (e.g. ``molecules=...``, ``executor=...`` for T-1).
        demo_spec: optional ``(spec_id) -> Spec`` for the no-proposal path -- the
            pre-built Spec a capability carries when the free-text parser cannot infer
            its precise DecisionRule (e.g. T-1's numeric threshold rule).
        demo_options: optional ``() -> dict`` giving the default ``experiment_fn``
            options for the demo path (e.g. T-1's designed molecule test set).
    """

    id: str
    experiment_fn: Callable[..., ExperimentFn]
    demo_spec: Optional[Callable[[str], Spec]] = None
    demo_options: Optional[Callable[[], dict]] = None

    @property
    def supports_demo(self) -> bool:
        """True when this capability can run with no proposal (demo Spec + options)."""
        return self.demo_spec is not None and self.demo_options is not None


# The single adapter-side registry. Keyed by capability id; populated by plugin
# registration at import time (T-1 below). The kernel has no handle to this dict.
_REGISTRY: Dict[str, CapabilityProvider] = {}


def register(provider: CapabilityProvider) -> None:
    """Register a capability provider under its id.

    Raises ``ValueError`` on a duplicate id: a second provider under an existing id
    would silently shadow the first, so we refuse rather than overwrite (the registry
    is the single source of truth for "which capability is this id").
    """
    if provider.id in _REGISTRY:
        raise ValueError(
            f"capability id '{provider.id}' is already registered; "
            f"registered: {sorted(_REGISTRY)}"
        )
    _REGISTRY[provider.id] = provider


def resolve(capability_id: str) -> CapabilityProvider:
    """Resolve a capability id to its provider.

    Raises a clear ``ValueError`` (listing ``available()``) on an unknown id so the
    caller can correct the selector without reading source.
    """
    try:
        return _REGISTRY[capability_id]
    except KeyError:
        raise ValueError(
            f"unknown capability '{capability_id}'; "
            f"available capabilities: {available()}"
        ) from None


def available() -> List[str]:
    """The registered capability ids (sorted, for a stable error/listing surface)."""
    return sorted(_REGISTRY)


# ---------------------------------------------------------------------------
# T-1 self-registration (the first capability, design §3.3). Importing this module
# registers it; the import lives in the adapter, so the kernel is untouched.
# ---------------------------------------------------------------------------

from sci_adk.adapter.t1_capability import (  # noqa: E402  (after registry API defined)
    T1_CAPABILITY_ID,
    build_t1_demo_molecules,
    build_t1_spec,
    t1_experiment,
)


def _t1_provider() -> CapabilityProvider:
    """Wrap the T-1 plugin's surface as a CapabilityProvider.

    ``experiment_fn`` forwards ``molecules`` (+ optional ``executor`` seam) to
    ``t1_experiment``; ``demo_spec`` is the real T-1 Spec; ``demo_options`` supplies the
    built-in designed molecule set. None of this couples the kernel to T-1.
    """

    def experiment_fn(**options) -> ExperimentFn:
        molecules = options["molecules"]
        executor = options.get("executor")
        return t1_experiment(molecules, executor=executor)

    return CapabilityProvider(
        id=T1_CAPABILITY_ID,
        experiment_fn=experiment_fn,
        demo_spec=build_t1_spec,
        demo_options=lambda: {"molecules": build_t1_demo_molecules()},
    )


# Idempotent under re-import (modules are cached, but guard anyway so a manual reload
# in a REPL/test does not raise the duplicate-id error).
if T1_CAPABILITY_ID not in _REGISTRY:
    register(_t1_provider())


__all__ = [
    "CapabilityProvider",
    "register",
    "resolve",
    "available",
]
