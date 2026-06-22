"""
``sci-adk init-session <dir>`` -- the Phase-3 research-workspace installer (D3).

design/research-session-enforcement.md D3 + sci-adk-as-moai.md §10.3/§10.5: install
the ``src/sci_adk/templates/research-workspace/`` kit into a target research
workspace, with one command, keeping the hook/``verify`` contracts version-pinned to
the sci-adk release. As of the sci-adk-as-moai Phase C upgrade the kit is the FULL
operational layer: the two enforcement hooks, the ``science-orchestrator`` output
style, ``CLAUDE.md``, a ``settings.json`` fragment, the 8 v1 worker/guard agents,
the 5 ``sci``/``science-*`` Skills, and the 7 ``/sci`` command routers. (The
``/research`` command and ``researcher`` persona were removed in the pivot;
``science-orchestrator`` is the sole installed persona and ``/sci`` is the sole entry
point.)

Two load-bearing invariants, tested explicitly in tests/test_init_session.py:

  - NON-CLOBBERING: a file the user already has is never overwritten. Identical
    content -> a no-op ("already current"); different content -> a "skipped"
    report and the user's file is left alone. The persona ``outputStyle`` and the
    two hook events merge into an EXISTING ``settings.json`` (never replacing it).
  - IDEMPOTENT: re-running the installer on the same dir changes nothing -- no
    duplicate hooks (matched by their ``command`` string), no file churn (an
    already-current file is not rewritten, so its mtime is stable), exit 0.

This module is pure-ish (stdlib + pydantic only): it reads the templates tree off
disk and writes into the target dir. It imports NO kernel experiment logic and --
critically -- NOT the paperforge adapter (the F4 seam stays green; this installer
is composition-root-adjacent, like ``cli.py``, not kernel code).

Templates root resolution: the kit ships as package data at
``sci_adk/templates/research-workspace/`` (via MANIFEST.in ``graft`` +
``include-package-data`` -- the hidden ``.claude/`` dir and the two ``.sh`` hooks
ride inside the wheel). ``_templates_root()`` resolves it with
``importlib.resources.files("sci_adk")`` so it works for BOTH an editable install
(``pip install -e .``) and a built wheel (unzipped into site-packages as a real
dir), with no ``__file__``-parents guessing.
"""

from __future__ import annotations

import importlib.resources
import json
import shutil
from pathlib import Path

from pydantic import BaseModel, Field

# --------------------------------------------------------------------------- #
# the kit's asset inventory (paths are relative to the templates root AND, by
# construction, identical relative to the target workspace).
# --------------------------------------------------------------------------- #

# plain file assets copied verbatim (non-clobbering). CLAUDE.md and settings.json
# have their own bespoke handling below and are NOT in this list. The ``/research``
# command and ``researcher`` persona were removed in the sci-adk-as-moai pivot; this
# list now installs the FULL kit -- the two enforcement hooks, the
# ``science-orchestrator`` output style, the 8 v1 worker/guard agents, the 5
# ``sci``/``science-*`` knowledge-library Skills, and the 7 ``/sci`` command routers.
# Every entry is copied through the same non-clobbering ``_copy_nonclobber`` path
# (the loop's ``dst.parent.mkdir(parents=True)`` creates ``.claude/agents/``,
# ``.claude/skills/<name>/`` and ``.claude/commands/sci/`` as needed -- no
# per-asset special-casing). Only the two hooks are executable
# (``_EXECUTABLE_ASSETS``); agents/skills/commands are plain data.
_PLAIN_ASSETS = (
    # enforcement hooks (Stop verify gate + UserPromptSubmit re-anchor)
    ".claude/hooks/sci-adk/stop-verify-gate.sh",
    ".claude/hooks/sci-adk/reanchor.sh",
    # the always-on persona
    ".claude/output-styles/science-orchestrator/science-orchestrator.md",
    # v1 worker agents (5)
    ".claude/agents/manager-prereg.md",
    ".claude/agents/expert-experimentalist.md",
    ".claude/agents/expert-statistician.md",
    ".claude/agents/expert-writer.md",
    ".claude/agents/expert-literature.md",
    # v1 guard agents (3) -- advisory; sci-adk verify is the sole verdict
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

# the subset of _PLAIN_ASSETS whose executable bit must be preserved (the hooks
# Claude Code execs). We force 0o755 on install rather than relying on the source
# bit surviving a checkout, so a git that stripped +x still yields runnable hooks.
_EXECUTABLE_ASSETS = frozenset(
    {
        ".claude/hooks/sci-adk/stop-verify-gate.sh",
        ".claude/hooks/sci-adk/reanchor.sh",
    }
)

_CLAUDE_MD = "CLAUDE.md"
# where the research protocol lands when the target already has its own CLAUDE.md
# (we never clobber a user's project-rules file; we leave a sidecar to @import).
_PROTOCOL_SIDECAR = ".claude/sci-adk-research-protocol.md"

_SETTINGS = ".claude/settings.json"

# the persona key the fragment wants (D3 / Layer 3).
_OUTPUT_STYLE = "science-orchestrator"
# the two hook events the fragment wires (D3 / Layers 1-2).
_HOOK_EVENTS = ("Stop", "UserPromptSubmit")


# --------------------------------------------------------------------------- #
# the report -- an immutable, structured record of every action taken (or, under
# --dry-run, every action that WOULD be taken). The CLI prints it and decides the
# exit code from it.
# --------------------------------------------------------------------------- #


class InstallReport(BaseModel):
    """A structured summary of an ``install_session`` run.

    Every field is a list of human-readable one-line action descriptions, grouped
    by outcome so the CLI can render them and pick an exit code:

    Attributes:
        installed: assets newly written (or, under dry-run, that WOULD be written).
        already_current: assets already byte-identical -> no-op (idempotent path).
        skipped: assets present but DIFFERING -> left intact (non-clobbering path).
        conflicts: soft warnings the user must resolve manually (e.g. an existing
            ``outputStyle`` that is not "science-orchestrator"); a conflict is NOT
            a failure.
        settings_changes: what the settings.json merge did (set outputStyle, added
            a hook, or "already current").
        dry_run: True iff nothing was written to disk.
    """

    installed: list[str] = Field(default_factory=list)
    already_current: list[str] = Field(default_factory=list)
    skipped: list[str] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)
    settings_changes: list[str] = Field(default_factory=list)
    dry_run: bool = False

    def lines(self) -> list[str]:
        """Render the report as ordered, prefixed lines for terminal output."""
        out: list[str] = []
        for label, items in (
            ("installed", self.installed),
            ("already current", self.already_current),
            ("skipped (exists, differs)", self.skipped),
            ("settings", self.settings_changes),
            ("conflict", self.conflicts),
        ):
            for item in items:
                out.append(f"  [{label}] {item}")
        return out


# --------------------------------------------------------------------------- #
# templates-root resolution
# --------------------------------------------------------------------------- #


def _templates_root() -> Path:
    """Return the ``research-workspace/`` template dir shipped with sci-adk.

    The kit is packaged as package data under ``sci_adk/templates/`` and resolved
    via ``importlib.resources.files("sci_adk")`` -- a real on-disk dir for BOTH an
    editable install and a built wheel (wheels are unzipped into site-packages).
    Raises a clear, friendly error if the dir is absent (a broken/partial install).
    """
    # importlib.resources.files -> the package's on-disk root (editable: <repo>/src/
    # sci_adk; wheel: site-packages/sci_adk). The templates ride inside it as data.
    root = (
        Path(str(importlib.resources.files("sci_adk")))
        / "templates"
        / "research-workspace"
    )
    if not root.is_dir():
        raise FileNotFoundError(
            "research-workspace templates not found at "
            f"{root}; the sci-adk install appears incomplete (the packaged "
            "templates are missing). Reinstall sci-adk (pip install -e . or the "
            "wheel)."
        )
    return root


# --------------------------------------------------------------------------- #
# non-clobbering file copy
# --------------------------------------------------------------------------- #


def _copy_nonclobber(
    src: Path,
    dst: Path,
    *,
    rel_label: str,
    executable: bool,
    dry_run: bool,
    report: InstallReport,
) -> None:
    """Copy ``src`` -> ``dst`` without ever clobbering an existing ``dst``.

    Three cases (the non-clobbering + idempotent contract):
      - ``dst`` absent           -> copy; report "installed".
      - ``dst`` byte-identical    -> no-op; report "already current" (NO rewrite,
                                     so mtime stays stable -> no churn on re-run).
      - ``dst`` present & differs -> DO NOT overwrite; report "skipped".

    ``executable`` forces ``0o755`` on a freshly installed file (the hooks).
    """
    src_bytes = src.read_bytes()

    if dst.exists():
        if dst.read_bytes() == src_bytes:
            report.already_current.append(rel_label)
        else:
            report.skipped.append(rel_label)
        return

    # new file -> install (unless dry-run, in which case only plan it).
    report.installed.append(rel_label)
    if dry_run:
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(src_bytes)
    if executable:
        # 0o755: rwx for owner, rx for group/other -- a runnable hook.
        dst.chmod(0o755)
    else:
        # preserve the source's mode for non-exec assets (harmless if it is 0o644).
        shutil.copymode(src, dst)


# --------------------------------------------------------------------------- #
# settings.json merge -- the fiddly core
# --------------------------------------------------------------------------- #


def _hook_group_for(event_fragment: dict) -> dict:
    """Return the single matcher-group object the fragment declares for an event."""
    # the fragment's value for an event is a list with exactly one matcher group.
    return event_fragment[0]


def _commands_in_event(target_event: list) -> set[str]:
    """All hook ``command`` strings already present across an event's groups."""
    cmds: set[str] = set()
    for group in target_event:
        for h in group.get("hooks", []):
            cmds.add(h.get("command", ""))
    return cmds


def _merge_settings(
    target: dict,
    fragment: dict,
    *,
    report: InstallReport,
) -> dict:
    """Merge the kit's ``settings.json`` ``fragment`` into ``target`` in place-ish.

    Returns the merged dict. Rules (D3 / Layer 1-3):

    - ``outputStyle``:
        absent       -> set it to the fragment's value ("science-orchestrator").
        == fragment  -> no-op (idempotent).
        other value  -> DO NOT overwrite; record a CONFLICT (a soft warning).
    - ``hooks.<event>`` for each of Stop / UserPromptSubmit:
        the fragment's hook is matched by its ``command`` string.
        present      -> no-op (no duplicate; idempotent).
        event exists with OTHER hooks -> APPEND ours (the user's hooks survive,
                        order preserved).
        event absent -> create it with our group.
    - all other target keys are preserved untouched.

    A deep copy of ``target`` is taken so the caller's input dict is never mutated.
    """
    merged = json.loads(json.dumps(target))  # cheap deep copy of JSON-shaped data

    # --- outputStyle ---
    want_style = fragment.get("outputStyle", _OUTPUT_STYLE)
    cur_style = merged.get("outputStyle")
    if cur_style is None:
        merged["outputStyle"] = want_style
        report.settings_changes.append(f"set outputStyle = '{want_style}'")
    elif cur_style == want_style:
        report.settings_changes.append(
            f"outputStyle already '{want_style}' (current)"
        )
    else:
        report.conflicts.append(
            f"outputStyle is '{cur_style}'; set it to '{want_style}' manually to "
            "enable the science-orchestrator persona (left intact)"
        )

    # --- hooks ---
    frag_hooks = fragment.get("hooks", {})
    merged_hooks = merged.setdefault("hooks", {})
    for event in _HOOK_EVENTS:
        if event not in frag_hooks:
            continue
        our_group = _hook_group_for(frag_hooks[event])
        # the command string that uniquely identifies our hook for this event.
        our_cmds = {
            h.get("command", "") for h in our_group.get("hooks", [])
        }

        target_event = merged_hooks.get(event)
        if target_event is None:
            # event absent -> create it with our group.
            merged_hooks[event] = [json.loads(json.dumps(our_group))]
            report.settings_changes.append(f"wired {event} hook")
            continue

        present = _commands_in_event(target_event)
        if our_cmds & present:
            # already present (matched by command) -> idempotent no-op, NO dup.
            report.settings_changes.append(f"{event} hook already present (current)")
        else:
            # event exists with OTHER hooks -> APPEND ours (preserve the user's).
            target_event.append(json.loads(json.dumps(our_group)))
            report.settings_changes.append(f"appended {event} hook (kept existing)")

    return merged


def _settings_equal(a: dict, b: dict) -> bool:
    """Stable structural equality (key order irrelevant)."""
    return json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


# --------------------------------------------------------------------------- #
# the build-harness guard (the incident class)
# --------------------------------------------------------------------------- #


def _refuse_if_build_harness(target: Path) -> None:
    """Raise if ``target`` (already resolved) looks like a build harness, not a
    research workspace.

    Refuses on EITHER of these markers (the two-environment rule):
      - ``target/src/sci_adk/``                -> the sci-adk build repo's package
        layout (a relative path that resolves into the repo root is covered here;
        the sci-adk build repo carries this marker, so it is still refused);
      - ``target/.claude/output-styles/moai/`` -> a MoAI build-harness marker.

    These two markers are the robust guard. (The former repo-root *identity* check
    was dropped when the templates moved INTO the package: ``_templates_root()`` no
    longer sits at a derivable repo root, and it cannot be computed for a wheel.)

    Never writes; this is a precondition gate.
    """
    if (target / "src" / "sci_adk").is_dir():
        raise NotADirectoryError(
            f"target {target} looks like the sci-adk build repo (has src/sci_adk/); "
            "install into a SEPARATE research workspace (two-environment rule)"
        )
    if (target / ".claude" / "output-styles" / "moai").is_dir():
        raise NotADirectoryError(
            f"target {target} looks like a MoAI build harness "
            "(has .claude/output-styles/moai/); install into a SEPARATE research "
            "workspace (two-environment rule)"
        )


# --------------------------------------------------------------------------- #
# the installer
# --------------------------------------------------------------------------- #


def install_session(target_dir: Path, *, dry_run: bool = False) -> InstallReport:
    """Install the research-workspace kit into ``target_dir`` (non-clobbering).

    See the module docstring for the two invariants (non-clobbering + idempotent).
    Returns an :class:`InstallReport`; raises ``NotADirectoryError`` if the target
    does not exist or is not a directory, and ``FileNotFoundError`` if the shipped
    templates cannot be located (non-editable install -- a Phase-3 follow-up).

    Args:
        target_dir: an existing research-workspace directory to install into.
        dry_run: when True, compute and report every planned action but write
            NOTHING to disk.
    """
    # An empty target silently resolves to the current directory (``Path("")`` and
    # ``Path(Path(""))`` both stringify to ``.``), which -- if a session ran this
    # from the sci-adk build repo -- would target the build workspace itself (the
    # exact two-environment dogfooding hazard the design doc warns against). Reject
    # an empty input explicitly rather than coercing to cwd. We test the raw input's
    # string form BEFORE Path normalization collapses "" -> "." (an explicit "." is a
    # deliberate, distinguishable choice and is allowed).
    if str(target_dir) in ("", "."):
        raise NotADirectoryError(
            "target directory is empty; pass an explicit research-workspace path"
        )
    target = Path(target_dir).resolve()
    if not target.exists():
        raise NotADirectoryError(f"target directory does not exist: {target}")
    if not target.is_dir():
        raise NotADirectoryError(f"target is not a directory: {target}")

    # BUILD-HARNESS guard (the incident class). The empty/`.` guard does NOT stop an
    # absolute (or relative-resolving) path INTO the sci-adk build repo / a MoAI build
    # harness -- installing the research gate there is the two-environment violation
    # the design doc forbids (the research verify gate and the build Stop/quality hooks
    # would fight). Refuse when the RESOLVED target carries any build-harness marker.
    # Because we resolved the path first, a relative path that lands on the repo root is
    # covered too (it gains the src/sci_adk/ marker). This is a TARGETED marker check --
    # legitimate relative workspace paths (no markers) still install normally.
    _refuse_if_build_harness(target)

    src_root = _templates_root()
    report = InstallReport(dry_run=dry_run)

    # 1. the plain file assets (hooks, science-orchestrator output style, the 8
    #    worker/guard agents, the 5 sci/science-* Skills, the 7 /sci commands).
    #    _copy_nonclobber's dst.parent.mkdir creates each needed subdir on the fly.
    for rel in _PLAIN_ASSETS:
        _copy_nonclobber(
            src_root / rel,
            target / rel,
            rel_label=rel,
            executable=(rel in _EXECUTABLE_ASSETS),
            dry_run=dry_run,
            report=report,
        )

    # 2. CLAUDE.md. Three cases (the third is what keeps re-runs idempotent):
    #      absent                   -> install it (we own the workspace's CLAUDE.md).
    #      present & == our template -> "already current" no-op. This is the file we
    #          installed on a PRIOR run; it must NOT trigger the sidecar path, or a
    #          second `init-session` would spawn a new sidecar (non-idempotent).
    #      present & DIFFERS         -> a user's own CLAUDE.md: leave it intact and
    #          drop our protocol into a sidecar they can @import / merge.
    src_claude = src_root / _CLAUDE_MD
    dst_claude = target / _CLAUDE_MD
    if not dst_claude.exists():
        _copy_nonclobber(
            src_claude, dst_claude, rel_label=_CLAUDE_MD,
            executable=False, dry_run=dry_run, report=report,
        )
    elif dst_claude.read_bytes() == src_claude.read_bytes():
        # our own previously-installed CLAUDE.md -> idempotent no-op.
        report.already_current.append(_CLAUDE_MD)
    else:
        # do NOT clobber the user's distinct CLAUDE.md; write the protocol to the
        # sidecar (same identical/differs non-clobbering logic) and tell the user.
        _copy_nonclobber(
            src_claude, target / _PROTOCOL_SIDECAR,
            rel_label=_PROTOCOL_SIDECAR,
            executable=False, dry_run=dry_run, report=report,
        )
        report.conflicts.append(
            f"existing {_CLAUDE_MD} left intact; research protocol written to "
            f"{_PROTOCOL_SIDECAR} -- merge/@import it into your {_CLAUDE_MD}"
        )

    # 3. settings.json -- load the target (or {} if absent), merge the fragment,
    #    write back pretty-printed unless dry-run / unchanged.
    fragment = json.loads((src_root / _SETTINGS).read_text(encoding="utf-8"))
    dst_settings = target / _SETTINGS
    if dst_settings.exists():
        # The user's existing settings.json may be hand-edited and malformed. A raw
        # json.JSONDecodeError here would surface as an ugly traceback; convert it to
        # a clean ValueError the CLI maps to a friendly non-zero exit. (JSONDecodeError
        # already subclasses ValueError, but we re-raise with a message that names the
        # offending file so the user knows exactly what to fix.)
        try:
            current = json.loads(dst_settings.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise ValueError(
                f"existing {_SETTINGS} is not valid JSON: {e}"
            ) from e
    else:
        current = {}
    merged = _merge_settings(current, fragment, report=report)

    if not dry_run and not _settings_equal(current, merged):
        dst_settings.parent.mkdir(parents=True, exist_ok=True)
        dst_settings.write_text(
            json.dumps(merged, indent=2) + "\n", encoding="utf-8"
        )

    return report
