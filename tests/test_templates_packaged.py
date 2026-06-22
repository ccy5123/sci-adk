"""Regression lock: the research-workspace kit is resolvable as package data.

The kit moved from a repo-root ``templates/`` dir (editable-install-only) INTO the
package at ``src/sci_adk/templates/research-workspace/`` and now ships as package
data (MANIFEST.in ``graft`` + ``include-package-data``), so ``sci-adk init-session``
works for a built wheel too -- not just an editable checkout.

These tests are the EDITABLE-mode lock: they assert ``_templates_root()`` resolves
to a real on-disk dir (via ``importlib.resources.files("sci_adk")``) and that every
asset the installer copies -- including the hidden ``.claude/`` tree and the two
``.sh`` hooks -- is present under it. The WHEEL-mode guarantee (that the same files
are actually inside the built ``.whl``) is verified out-of-band by a real
``pip wheel`` build during development; here we lock the resolver + inventory so a
future move/rename that breaks the editable path fails loudly.
"""

from __future__ import annotations

import stat

from sci_adk.init_session import _templates_root

# The complete asset inventory the installer lays down (kept in lockstep with
# init_session._PLAIN_ASSETS + CLAUDE.md + settings.json). If the kit grows an
# asset, add it here so the packaging lock stays exhaustive. README.md is packaged
# (rides in the wheel) but is NOT installed by the verb -- it documents the source
# kit; it stays in this inventory because this test only asserts presence under the
# templates root, not installation.
_KIT_FILES = (
    "CLAUDE.md",
    "README.md",
    ".claude/settings.json",
    ".claude/output-styles/science-orchestrator/science-orchestrator.md",
    ".claude/hooks/sci-adk/stop-verify-gate.sh",
    ".claude/hooks/sci-adk/reanchor.sh",
    # v1 worker agents (5)
    ".claude/agents/manager-prereg.md",
    ".claude/agents/expert-experimentalist.md",
    ".claude/agents/expert-statistician.md",
    ".claude/agents/expert-writer.md",
    ".claude/agents/expert-literature.md",
    # v1 guard agents (3)
    ".claude/agents/evaluator-rigor.md",
    ".claude/agents/evaluator-novelty.md",
    ".claude/agents/evaluator-validity.md",
    # the sci orchestration hub + 4 knowledge-library Skills
    ".claude/skills/sci/SKILL.md",
    ".claude/skills/science-foundation-rigor/SKILL.md",
    ".claude/skills/science-workflow-prereg/SKILL.md",
    ".claude/skills/science-workflow-experiment/SKILL.md",
    ".claude/skills/science-workflow-publish/SKILL.md",
    # /sci thin command routers (root + 6 subcommands)
    ".claude/commands/sci.md",
    ".claude/commands/sci/plan.md",
    ".claude/commands/sci/experiment.md",
    ".claude/commands/sci/publish.md",
    ".claude/commands/sci/verify.md",
    ".claude/commands/sci/status.md",
    ".claude/commands/sci/replicate.md",
)
_HOOK_SCRIPTS = (
    ".claude/hooks/sci-adk/stop-verify-gate.sh",
    ".claude/hooks/sci-adk/reanchor.sh",
)


def test_templates_root_is_a_real_dir():
    root = _templates_root()
    assert root.is_dir(), f"_templates_root() is not a real dir: {root}"


def test_every_kit_asset_is_present_under_templates_root():
    root = _templates_root()
    for rel in _KIT_FILES:
        assert (root / rel).is_file(), f"packaged kit is missing asset: {rel}"


def test_hidden_dotclaude_tree_is_packaged():
    # the gotcha the packaging guards against: a hidden `.claude/` dir that a plain
    # glob would skip. Assert the dir AND a file inside it both resolve.
    root = _templates_root()
    assert (root / ".claude").is_dir(), "packaged kit is missing the .claude/ tree"
    assert (root / ".claude" / "settings.json").is_file()


def test_packaged_hooks_carry_the_executable_bit():
    # the source-tree hooks ship +x (the installer re-forces 0o755 on install, but
    # the SOURCE bit surviving the package move is what this locks).
    root = _templates_root()
    for rel in _HOOK_SCRIPTS:
        mode = (root / rel).stat().st_mode
        assert mode & stat.S_IXUSR, f"packaged hook lost its user-x bit: {rel}"
        assert mode & 0o111, f"packaged hook is not executable at all: {rel}"


def test_settings_json_wires_the_two_hook_events():
    # a smoke check that the packaged settings fragment is the real one (not an
    # empty placeholder): it must name both hook events.
    import json

    settings = json.loads(
        (_templates_root() / ".claude" / "settings.json").read_text(encoding="utf-8")
    )
    hooks = settings.get("hooks", {})
    assert "Stop" in hooks
    assert "UserPromptSubmit" in hooks
