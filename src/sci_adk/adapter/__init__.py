"""
sci-adk capability adapter layer.

This package is the capability-adapter seam from the agreed rigor-shell
architecture (design/rigor-shell-architecture.md §3, F4). All domain- and
capability-specific behavior lives HERE, behind the kernel's three interfaces
(Verifier / Experiment / Judge).

Dependency direction is ONE-WAY: ``adapter -> kernel`` is allowed; the kernel
(``sci_adk.core``, ``sci_adk.loop``, ``sci_adk.render``) MUST NOT import from
``sci_adk.adapter`` (design §2.4). The first registered capability is the T-1
molecular Gödel encoding (``t1_capability`` + ``t1_encoding``), which replaces the
milestone-1 toy that lived in ``sci_adk.loop.compiler``.
"""

__all__: list[str] = []
