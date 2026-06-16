"""
F4 seam lint (RED-first): the build-failing tripwire that enforces the ONE-WAY
kernel/adapter dependency (design/rigor-shell-architecture.md §2.4, §3, §8 F4).

The rigor kernel (``sci_adk.core``, ``sci_adk.loop``, ``sci_adk.render``) MUST NOT
import from ``sci_adk.adapter``. ``adapter -> kernel`` is allowed; ``kernel -> adapter``
is forbidden. Today that is convention; this module makes it an *enforced* invariant
that runs on every ``pytest`` -- a kernel module that grows an adapter import FAILS
the build.

Two assertions make this trustworthy, not a tautology:
  1. ``test_kernel_is_clean``: AST-parses every ``.py`` under core/loop/render on the
     real filesystem and asserts ZERO of them import ``sci_adk.adapter``. The kernel is
     already clean, so this passes today; it catches any future violation.
  2. ``test_lint_flags_a_synthetic_violation`` (the TRIP-CASE): feeds the checker a
     *synthetic* module source that DOES ``import sci_adk.adapter`` and asserts the
     checker reports it. Without this, a passing lint could be a no-op. We never add a
     real violating import to the kernel -- the trip is proven against a fixture string.

The checker resolves BOTH absolute (``sci_adk.adapter``) and relative (``..adapter``)
import forms via ``node.level`` -- ignoring ``node.level`` would let a relative adapter
import bypass the lint silently (false safety).

The scan is scoped to core/loop/render, so ``cli.py`` (the composition root, allowed to
import the adapter) and the ``adapter`` package itself are *naturally* outside it. There
is essentially NO exclude list: a kernel module that "needs" an adapter import is a
design smell to FIX, never to except (treated with the same discipline as never
weakening the F2 trail gate to make a test pass).

Honest limit: this is a static AST checker over ``import`` / ``from ... import``
statements only. Dynamic imports via ``importlib.import_module(...)`` / ``__import__(...)``
are Call nodes and are NOT covered -- a literal-string argument is an acknowledged
residual, and a runtime-computed module name is undetectable by any static tool; a kernel
module reaching the adapter through a computed import is itself a design violation caught
in review, not by this lint.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import List, Tuple

import sci_adk


# The kernel packages the seam protects. The adapter and the CLI are deliberately
# absent: adapter -> kernel is allowed, and cli.py is the composition root.
_KERNEL_PACKAGES = ("core", "loop", "render")

_FORBIDDEN_ROOT = "sci_adk.adapter"


def _is_forbidden(absolute: str) -> bool:
    """True iff ``absolute`` is ``sci_adk.adapter`` or a submodule of it.

    The submodule check requires a trailing dot so ``sci_adk.adapterless_helper`` and
    ``sci_adk.search.paperforge_adapter`` (look-alikes) do NOT match.
    """
    return absolute == _FORBIDDEN_ROOT or absolute.startswith(_FORBIDDEN_ROOT + ".")


def _relative_base(modname: str, level: int, *, is_package: bool) -> str:
    """Resolve the base package a relative import of ``level`` dots refers to.

    Python semantics: ``from .`` (level 1) is the *current package*. For a regular
    module ``sci_adk.loop.foo`` the current package is ``sci_adk.loop`` (drop the final
    component); for a package's ``__init__`` (``is_package``) the current package is the
    package itself (no drop). Each additional level drops one more trailing component.

    Returns "" if the relative reference walks above the top-level package (an
    unresolvable/invalid relative import -- treated as no match here).
    """
    parts = modname.split(".")
    # level 1 base: the package containing the module (or the package itself for __init__).
    drop = level if not is_package else (level - 1)
    if drop > len(parts):
        return ""
    base_parts = parts[: len(parts) - drop] if drop else parts
    return ".".join(base_parts)


def find_adapter_imports(
    source: str, modname: str, *, is_package: bool = False
) -> List[Tuple[str, str]]:
    """Return ``(modname, resolved_module)`` for every import of ``sci_adk.adapter``
    (or a submodule) in ``source`` -- absolute OR relative.

    This is the lint's core check, factored out so the TRIP-CASEs can feed it synthetic
    source strings. It catches every import form:
      - ``import sci_adk.adapter`` / ``import sci_adk.adapter.x`` (ast.Import)
      - ``from sci_adk.adapter import x`` / ``from sci_adk.adapter.x import y`` (absolute ImportFrom)
      - ``from ..adapter import x`` / ``from ..adapter.x import y`` (relative ImportFrom)
      - ``from .. import adapter`` (relative ImportFrom, module=None: the imported NAME
        resolves against the parent package)

    Relative imports are resolved to their absolute module via ``node.level`` + ``modname``
    (``is_package`` distinguishes an ``__init__``). Ignoring ``node.level`` -- as a naive
    absolute-string comparison does -- would let a relative ``..adapter`` import bypass
    the lint silently (false safety). An empty list means the source is seam-clean.
    """
    offenders: List[Tuple[str, str]] = []
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            # `import X` is always absolute (no level concept).
            for alias in node.names:
                if _is_forbidden(alias.name):
                    offenders.append((modname, alias.name))
        elif isinstance(node, ast.ImportFrom):
            level = node.level or 0
            if level == 0:
                # Absolute: `from sci_adk.adapter[.x] import ...`.
                mod = node.module or ""
                if _is_forbidden(mod):
                    offenders.append((modname, mod))
                continue
            # Relative: resolve node.level against the scanned module's dotted name.
            base = _relative_base(modname, level, is_package=is_package)
            if not base:
                continue
            if node.module:
                # `from ..adapter[.x] import names` -> base + "." + node.module.
                resolved = f"{base}.{node.module}"
                if _is_forbidden(resolved):
                    offenders.append((modname, resolved))
            else:
                # `from .. import names` -> each imported NAME hangs off the base package.
                for alias in node.names:
                    resolved = f"{base}.{alias.name}"
                    if _is_forbidden(resolved):
                        offenders.append((modname, resolved))
    return offenders


def _kernel_modules() -> List[Tuple[Path, str, bool]]:
    """Every ``.py`` under the kernel packages as ``(path, dotted_modname, is_package)``.

    Scanning files (not a hardcoded module list) means a NEW kernel module is covered
    automatically -- the tripwire cannot be silently bypassed by adding a file. The
    dotted module name (derived from the path relative to the ``sci_adk`` parent) is
    REQUIRED so the checker can resolve any relative ``..adapter`` import; ``is_package``
    flags ``__init__.py`` so its relative-import base is the package itself.
    """
    pkg_root = Path(sci_adk.__file__).resolve().parent  # .../src/sci_adk
    src_root = pkg_root.parent                           # .../src  (so paths -> sci_adk.*)
    out: List[Tuple[Path, str, bool]] = []
    for pkg in _KERNEL_PACKAGES:
        for path in sorted((pkg_root / pkg).rglob("*.py")):
            rel = path.resolve().relative_to(src_root)
            is_pkg = path.name == "__init__.py"
            if is_pkg:
                dotted = ".".join(rel.parent.parts)            # sci_adk.loop
            else:
                dotted = ".".join(rel.with_suffix("").parts)   # sci_adk.loop.compiler
            out.append((path, dotted, is_pkg))
    return out


class TestKernelIsClean:
    """The real kernel must not import the adapter (the enforced invariant)."""

    def test_kernel_packages_exist(self):
        # Guard: if the scan finds no files, the lint would vacuously pass. Prove the
        # packages are present and non-empty so a passing lint means something.
        mods = _kernel_modules()
        assert mods, "no kernel .py files found -- the seam scan would be vacuous"
        scanned = {path.parent.name for path, _dotted, _pkg in mods}
        for pkg in _KERNEL_PACKAGES:
            assert pkg in scanned, f"kernel package '{pkg}' produced no scanned files"

    def test_kernel_is_clean(self):
        offenders: List[Tuple[str, str]] = []
        for path, dotted, is_pkg in _kernel_modules():
            source = path.read_text(encoding="utf-8")
            offenders.extend(
                find_adapter_imports(source, dotted, is_package=is_pkg)
            )
        assert offenders == [], (
            "kernel -> adapter import FORBIDDEN (design §2.4/F4); offenders: "
            f"{offenders}. Fix the coupling -- do NOT add an exception."
        )


class TestLintIsNotANoOp:
    """The TRIP-CASE: prove the checker actually flags a violation (anti-tautology)."""

    def test_lint_flags_import_statement(self):
        # A synthetic kernel module that imports the adapter via `import ...`.
        violating = "import sci_adk.adapter\n\nx = 1\n"
        offenders = find_adapter_imports(violating, "sci_adk.loop.fake_kernel_mod")
        assert offenders == [("sci_adk.loop.fake_kernel_mod", "sci_adk.adapter")]

    def test_lint_flags_submodule_import(self):
        violating = "import sci_adk.adapter.t1_capability as cap\n"
        offenders = find_adapter_imports(violating, "fake")
        assert offenders == [("fake", "sci_adk.adapter.t1_capability")]

    def test_lint_flags_from_import(self):
        violating = "from sci_adk.adapter.registry import resolve\n"
        offenders = find_adapter_imports(violating, "fake")
        assert offenders == [("fake", "sci_adk.adapter.registry")]

    def test_lint_flags_from_package_import(self):
        violating = "from sci_adk.adapter import t1_capability\n"
        offenders = find_adapter_imports(violating, "fake")
        assert offenders == [("fake", "sci_adk.adapter")]

    def test_lint_passes_clean_source(self):
        # A look-alike that must NOT trip: a different package whose name merely
        # starts with the same letters, and a legitimate kernel import.
        clean = (
            "from sci_adk.core.spec import Spec\n"
            "import sci_adk.adapterless_helper\n"  # NOT sci_adk.adapter(.*)
            "from sci_adk.loop.compiler import ResearchCompiler\n"
        )
        assert find_adapter_imports(clean, "fake") == []

    # -- RELATIVE-import forms (the bypass the absolute-string checker missed) ------
    # These resolve `node.level` against the SCANNED module's dotted name. A kernel
    # module writing a relative ..adapter import is exactly as forbidden as an absolute
    # one; the checker must catch both or it offers false safety.

    def test_lint_flags_relative_from_adapter_package(self):
        # `from ..adapter import registry` in sci_adk/loop/foo.py
        # level=2 walks up 2 from sci_adk.loop.foo -> sci_adk, +"adapter" -> sci_adk.adapter.
        violating = "from ..adapter import registry\n"
        offenders = find_adapter_imports(violating, "sci_adk.loop.foo")
        assert offenders == [("sci_adk.loop.foo", "sci_adk.adapter")]

    def test_lint_flags_relative_from_adapter_submodule(self):
        # `from ..adapter.registry import resolve` in sci_adk/core/x.py -> sci_adk.adapter.registry
        violating = "from ..adapter.registry import resolve\n"
        offenders = find_adapter_imports(violating, "sci_adk.core.x")
        assert offenders == [("sci_adk.core.x", "sci_adk.adapter.registry")]

    def test_lint_flags_relative_from_parent_importing_name(self):
        # `from .. import adapter` in sci_adk/loop/foo.py: module=None, the imported NAME
        # "adapter" off the parent package sci_adk -> sci_adk.adapter. The checker must
        # inspect the imported names against the parent package, not only node.module.
        violating = "from .. import adapter\n"
        offenders = find_adapter_imports(violating, "sci_adk.loop.foo")
        assert offenders == [("sci_adk.loop.foo", "sci_adk.adapter")]

    def test_lint_flags_relative_within_package_init(self):
        # `from .adapter import registry` in sci_adk/__init__.py: level=1 within the
        # package -> sci_adk.adapter. The modname IS the package itself, so the scan
        # marks it is_package=True (an __init__'s "current package" is itself, with no
        # final component dropped).
        violating = "from .adapter import registry\n"
        offenders = find_adapter_imports(violating, "sci_adk", is_package=True)
        assert offenders == [("sci_adk", "sci_adk.adapter")]

    def test_lint_does_not_overmatch_relative_search_adapter(self):
        # FALSE-POSITIVE guard: `from ..search import paperforge_adapter` in
        # sci_adk/loop/x.py resolves to sci_adk.search.paperforge_adapter -- that is
        # sci_adk.search, NOT sci_adk.adapter. The resolver must not over-match a module
        # whose *name* merely ends in "_adapter" or contains "adapter".
        clean = "from ..search import paperforge_adapter\n"
        assert find_adapter_imports(clean, "sci_adk.loop.x") == []

    def test_lint_does_not_overmatch_relative_name_paperforge_adapter(self):
        # The same look-alike via the parent-import form: `from ..search import
        # paperforge_adapter` already covered; also guard `from .. import
        # search` style won't false-trip (imported name "search" off sci_adk.loop ->
        # sci_adk.search, not adapter).
        clean = "from .. import literature_acquirer\n"
        assert find_adapter_imports(clean, "sci_adk.loop.x") == []
