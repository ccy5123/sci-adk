"""
paperforge adapter -- DOI -> Open Access PDF acquisition via the paperforge CLI.

sci-adk invokes paperforge as a *subprocess* (mirroring runner/docker_executor.py)
rather than importing it. This keeps the two Python environments decoupled
(sci-adk on system python, paperforge pinned via git) and captures provenance
for reproducibility -- the acquisition step records exactly which tool version
and command produced each PDF.

paperforge resolves each DOI through an Open-Access fallback chain
(arXiv -> Unpaywall -> OpenAlex -> Europe PMC -> Semantic Scholar), verifies
every download by its ``%PDF-`` magic bytes, and writes a resumable
``manifest.csv`` plus a per-PDF ``.json`` sidecar.

Scope (two-environment separation, design/tool-policy.md addendum 2026-06-16):
    This is sci-adk *acquisition* tooling. It is governed by the tool policy
    (recorded acquisition tool, user-approved) -- it acquires the record
    (papers), it does not judge belief. No success metric is hardcoded here.

Pin: ccy5123/paperforge @ 2cec69b5c9e3cdd518463a24f67cf713ff3f0d9e
    (feature branch tip: metadata enrichment + citation-style filenames).
    Declared in pyproject.toml as the optional ``tools`` dependency group;
    install with ``pip install -e ".[tools]"``.

Which executable runs (see :func:`resolve_paperforge_bin`): ``$SCI_ADK_PAPERFORGE``,
else ``[literature] paperforge`` in the sci-adk config file, else the ``paperforge``
beside the running sci-adk, else PATH. Provenance records the path that ran, the rule
that chose it, and the version that tool reports -- the pin above is only what
pyproject declares.
"""

from __future__ import annotations

import csv
import os
import shlex
import shutil
import subprocess
import sys
import sysconfig
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Sequence

# The git SHA pyproject.toml's [tools] group pins paperforge to. It states what a
# `pip install -e ".[tools]"` installs, NOT what a given run executed (that is
# ``tool_path`` / ``tool_version`` in provenance). Keep in sync with pyproject.toml.
PINNED_SHA = "2cec69b5c9e3cdd518463a24f67cf713ff3f0d9e"

# Environment variable naming the exact paperforge executable (absolute path).
ENV_VAR = "SCI_ADK_PAPERFORGE"

# Resolution rule labels, recorded in provenance as ``tool_resolved_by``.
RULE_ARGUMENT = "argument"
RULE_ENV = f"env:{ENV_VAR}"
RULE_CONFIG = "config:[literature] paperforge"
RULE_SCI_ADK_DIR = "sci-adk-dir"
RULE_PATH = "PATH"

# Seconds allowed for each version probe (local process start only, no network).
_VERSION_PROBE_TIMEOUT = 15

# Run by the tool's own interpreter when it has no ``--version``: the installed
# distribution's version, plus the git commit when it was installed from git.
_DIST_VERSION_PROBE = (
    "import importlib.metadata as m, json\n"
    "d = m.distribution('paperforge')\n"
    "try:\n"
    "    c = json.loads(d.read_text('direct_url.json') or '{}')"
    ".get('vcs_info', {}).get('commit_id')\n"
    "except Exception:\n"
    "    c = None\n"
    "print(d.version + (' git ' + c if c else ''))\n"
)

# Columns paperforge writes to manifest.csv (paperforge orchestrator.py).
_MANIFEST_FIELDS = ("index", "doi", "status", "source", "license",
                    "filename", "origin", "error")

# paperforge CLI exit codes (paperforge cli.py main()).
EXIT_OK = 0          # every DOI resolved to a downloaded PDF
EXIT_SOME_FAILED = 1  # at least one DOI failed (a valid partial outcome)
EXIT_NO_DOIS = 2      # no DOIs found in the given inputs


@dataclass(frozen=True)
class AcquisitionRecord:
    """One DOI's outcome, parsed from a manifest.csv row."""

    doi: str
    status: str          # "success" | "failed"
    source: str = ""     # winning OA source (arxiv/unpaywall/openalex/...)
    license: str = ""
    filename: str = ""
    error: str = ""

    @property
    def ok(self) -> bool:
        return self.status == "success"


@dataclass
class AcquisitionResult:
    """The outcome of one paperforge run: per-DOI records + provenance."""

    returncode: int
    output_dir: Path
    manifest_path: Path
    records: list[AcquisitionRecord] = field(default_factory=list)
    provenance: dict[str, Any] = field(default_factory=dict)
    stdout: str = ""
    stderr: str = ""

    @property
    def succeeded(self) -> list[AcquisitionRecord]:
        return [r for r in self.records if r.ok]

    @property
    def failed(self) -> list[AcquisitionRecord]:
        return [r for r in self.records if not r.ok]


class PaperforgeNotInstalled(RuntimeError):
    """Raised when no paperforge executable was found by any resolution rule."""


class AcquisitionToolError(RuntimeError):
    """The acquisition tool failed to run, so this call produced no record.

    Distinct from a DOI with no OA PDF (a recorded null, ``EXIT_SOME_FAILED``):
    this is a broken run -- an exit code outside {0, 1}, or a run whose manifest
    carries none of the requested DOIs. Raised BEFORE any Evidence is written.
    """

    STDERR_TAIL_LINES = 10

    def __init__(self, message: str, *, returncode: int, stderr: str = "") -> None:
        self.returncode = returncode
        lines = (stderr or "").strip().splitlines()
        self.stderr_tail = "\n".join(lines[-self.STDERR_TAIL_LINES:])
        super().__init__(message)


class PaperforgePathError(AcquisitionToolError):
    """An explicitly configured paperforge path is unusable (relative, missing, or not
    executable). Raised instead of falling back to another paperforge, so a pinned
    choice is never silently replaced. Like its parent, it is raised before any
    Evidence is written; ``returncode`` 127 is the shell's "command not found"."""

    def __init__(self, message: str) -> None:
        super().__init__(message, returncode=127)


def _is_executable_file(path: Path) -> bool:
    return path.is_file() and os.access(path, os.X_OK)


def _explicit_bin(value: str, rule: str) -> str:
    """Validate an explicitly configured path; raise rather than fall through."""
    path = Path(value).expanduser()
    where = f"${ENV_VAR}" if rule == RULE_ENV else "[literature] paperforge in the config file"
    if not path.is_absolute():
        raise PaperforgePathError(
            f"paperforge path from {where} must be an absolute path, got {value!r}")
    if not path.exists():
        raise PaperforgePathError(f"paperforge path from {where} does not exist: {path}")
    if not _is_executable_file(path):
        raise PaperforgePathError(
            f"paperforge path from {where} is not executable: {path}")
    return str(path)


def _sci_adk_script_dirs() -> list[Path]:
    """Directories that hold the running sci-adk: its console script's own dir first
    (exact for user installs, where the interpreter's scheme dir is a system dir),
    then the interpreter's scripts dir."""
    dirs: list[Path] = []
    if sys.argv and sys.argv[0]:
        dirs.append(Path(sys.argv[0]).resolve().parent)
    scripts = sysconfig.get_path("scripts")
    if scripts:
        dirs.append(Path(scripts))
    unique: list[Path] = []
    for d in dirs:
        if d not in unique:
            unique.append(d)
    return unique


def resolve_paperforge_bin(
    config_root: Optional[Path] = None,
) -> tuple[Optional[str], Optional[str]]:
    """Choose the paperforge executable and say which rule chose it.

    Order: ``$SCI_ADK_PAPERFORGE``; ``[literature] paperforge`` in the sci-adk config;
    a ``paperforge`` in the directory of the running sci-adk (console-script dir, then
    the interpreter's scripts dir); ``shutil.which("paperforge")``. An explicit value
    (the first two) that is unusable raises :class:`PaperforgePathError`.

    Returns:
        ``(absolute path, rule label)``, or ``(None, None)`` when nothing is found.
    """
    # @MX:NOTE: [AUTO] explicit settings never fall through: a stale pin must fail loudly
    #   instead of silently running whichever paperforge PATH offers (an unrelated
    #   program of the same name came first on PATH in some shells).
    from sci_adk.config import paperforge_path

    env_value = os.environ.get(ENV_VAR, "").strip()
    if env_value:
        return _explicit_bin(env_value, RULE_ENV), RULE_ENV
    cfg_value = paperforge_path(config_root)
    if cfg_value:
        return _explicit_bin(cfg_value, RULE_CONFIG), RULE_CONFIG

    names = ("paperforge.exe", "paperforge") if os.name == "nt" else ("paperforge",)
    for directory in _sci_adk_script_dirs():
        for name in names:
            candidate = directory / name
            if _is_executable_file(candidate):
                return str(candidate), RULE_SCI_ADK_DIR

    found = shutil.which("paperforge")
    if found:
        return os.path.abspath(found), RULE_PATH
    return None, None


def _python_shebang(path: Path) -> Optional[list[str]]:
    """The interpreter argv on ``path``'s ``#!`` line when it is a Python, else None."""
    try:
        with open(path, "rb") as f:
            first = f.readline(512).decode("utf-8", "strict").strip()
    except (OSError, UnicodeDecodeError):
        return None
    if not first.startswith("#!"):
        return None
    try:
        argv = shlex.split(first[2:])
    except ValueError:
        return None
    if argv and Path(argv[0]).name == "env":
        argv = [a for a in argv[1:] if not a.startswith("-")]
    if not argv or not Path(argv[0]).name.startswith("python"):
        return None
    return argv


def probe_tool_version(tool_path: Optional[str]) -> str:
    """The version the paperforge at ``tool_path`` reports, or ``"unknown"``.

    First ``<tool> --version`` (first non-blank stdout line on exit 0). paperforge has
    no ``--version`` today, so when that yields nothing and the tool is a Python console
    script, its own interpreter (from the shebang) is asked for the installed
    ``paperforge`` distribution version and git commit. Local processes only; any
    failure gives ``"unknown"``.
    """
    if not tool_path:
        return "unknown"
    attempts: list[list[str]] = [[tool_path, "--version"]]
    interpreter = _python_shebang(Path(tool_path))
    if interpreter:
        attempts.append([*interpreter, "-c", _DIST_VERSION_PROBE])
    for argv in attempts:
        try:
            proc = subprocess.run(argv, capture_output=True, text=True,
                                  timeout=_VERSION_PROBE_TIMEOUT)
        except (OSError, subprocess.SubprocessError, ValueError):
            continue
        if proc.returncode != 0:
            continue
        for line in (proc.stdout or "").splitlines():
            if line.strip():
                return line.strip()
    return "unknown"


def _stat_signature(path: Path) -> Optional[tuple[int, int]]:
    """``(mtime_ns, size)`` of ``path``, or None when absent -- detects a rewrite."""
    try:
        st = path.stat()
    except FileNotFoundError:
        return None
    return (st.st_mtime_ns, st.st_size)


class PaperforgeAdapter:
    """
    Acquire Open-Access PDFs for a set of DOIs by driving the paperforge CLI.

    The adapter holds no acquisition policy of its own: every knob (OA source
    order, license filter, metadata enrichment) is passed through to the tool,
    and the per-DOI verdicts come back verbatim from paperforge's manifest. The
    adapter's job is to build a reproducible command, run it, and parse the
    record -- the same record/provenance discipline runner/docker_executor.py
    applies to experiments.
    """

    def __init__(
        self,
        paperforge_bin: Optional[str] = None,
        email: Optional[str] = None,
        timeout: int = 600,
        *,
        config_root: Optional[Path] = None,
    ) -> None:
        """
        Args:
            paperforge_bin: path to the ``paperforge`` executable, used as given.
                When None it is chosen by :func:`resolve_paperforge_bin`.
            email: contact email for the Unpaywall/OpenAlex polite pool. When
                None, paperforge falls back to ``$UNPAYWALL_EMAIL`` and, if that
                is also unset, skips Unpaywall (weaker results).
            timeout: subprocess timeout in seconds (a batch can be slow).
            config_root: override the sci-adk config root (tests).

        Raises:
            PaperforgePathError: an explicitly configured path is unusable.
        """
        if paperforge_bin:
            self.paperforge_bin: Optional[str] = paperforge_bin
            self.resolved_by: Optional[str] = RULE_ARGUMENT
        else:
            self.paperforge_bin, self.resolved_by = resolve_paperforge_bin(config_root)
        self.email = email
        self.timeout = timeout

    # -- contact email resolution (evidence-validity E4) -------------------

    def resolve_email(
        self,
        *,
        require: bool = False,
        config_root: Optional[Path] = None,
    ) -> Optional[str]:
        """Resolve the contact email from (this adapter's ``email`` -> sci-adk config
        -> ``$UNPAYWALL_EMAIL``).

        design/evidence-validity.md E4: when ``require`` is True and no source supplies
        an email, this raises ``ConfigHalt`` (a clear, how-to-fix message) rather than
        letting acquisition run silently degraded (no ``--email`` -> weaker OA results,
        the degraded-acquisition failure). When ``require`` is False it returns
        ``None`` on absence (the legacy permissive behavior, for callers that tolerate
        the degraded pool).

        Args:
            require: halt with ``ConfigHalt`` when no email can be resolved.
            config_root: override the config root (tests).

        Returns:
            The resolved email, or ``None`` when absent and ``require`` is False.
        """
        # Imported lazily so importing the adapter never requires the config module.
        from sci_adk.config import ConfigHalt, resolve_contact_email

        try:
            return resolve_contact_email(self.email, config_root=config_root)
        except ConfigHalt:
            if require:
                raise
            return None

    # -- command construction (pure; unit-tested without network) ----------

    def build_command(
        self,
        dois: Sequence[str],
        output_dir: Path,
        *,
        source_order: Optional[Sequence[str]] = None,
        licenses: Optional[Sequence[str]] = None,
        require_known_license: bool = False,
        no_metadata: bool = False,
        overwrite: bool = False,
        verbose: bool = False,
    ) -> list[str]:
        """
        Build the ``paperforge`` argv for the given DOIs and options.

        Pure function: no I/O, no network -- so it is fully unit-testable. DOIs
        always begin with ``10.`` so they never collide with option flags.
        """
        if self.paperforge_bin is None:
            raise PaperforgeNotInstalled(
                "paperforge CLI not found (not beside sci-adk, not on PATH); install "
                'it with pip install -e ".[tools]" (pins ccy5123/paperforge@'
                f"{PINNED_SHA[:7]}), or name it with ${ENV_VAR} / "
                "[literature] paperforge in the sci-adk config file"
            )
        cmd: list[str] = [self.paperforge_bin, *dois, "-o", str(output_dir)]
        if self.email:
            cmd += ["--email", self.email]
        if source_order:
            cmd += ["--source-order", ",".join(source_order)]
        if licenses:
            cmd += ["--licenses", ",".join(licenses)]
        if require_known_license:
            cmd += ["--require-known-license"]
        if no_metadata:
            cmd += ["--no-metadata"]
        if overwrite:
            cmd += ["--overwrite"]
        if verbose:
            cmd += ["--verbose"]
        return cmd

    # -- manifest parsing (pure; unit-tested without network) --------------

    @staticmethod
    def parse_manifest(manifest_path: Path) -> list[AcquisitionRecord]:
        """
        Parse paperforge's ``manifest.csv`` into ``AcquisitionRecord``s.

        Returns an empty list when the manifest is absent (e.g. the run found
        no DOIs and exited before writing one).
        """
        if not manifest_path.exists():
            return []
        records: list[AcquisitionRecord] = []
        with open(manifest_path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                records.append(
                    AcquisitionRecord(
                        doi=row.get("doi", ""),
                        status=row.get("status", ""),
                        source=row.get("source", ""),
                        license=row.get("license", ""),
                        filename=row.get("filename", ""),
                        error=row.get("error", ""),
                    )
                )
        return records

    # -- execution (subprocess; smoke-tested with a real DOI) --------------

    def fetch(
        self,
        dois: Sequence[str],
        output_dir: Path,
        **options: Any,
    ) -> AcquisitionResult:
        # @MX:ANCHOR: [AUTO] external-system integration point (paperforge CLI)
        # @MX:REASON: [AUTO] sole boundary where sci-adk acquires full-text PDFs
        #   from an external tool + network OA services; the (dois, options) ->
        #   AcquisitionResult contract and the captured provenance are what every
        #   downstream acquisition step and the research loop will depend on.
        """
        Acquire OA PDFs for ``dois`` into ``output_dir`` via paperforge.

        ``EXIT_SOME_FAILED`` is NOT an error: some DOIs had no downloadable OA
        PDF -- a valid, recordable outcome (a null result is still a result).
        The per-DOI verdicts are in ``result.records``; inspect
        ``result.succeeded`` / ``result.failed``. The adapter does not judge the
        return code; ``LiteratureAcquirer`` rejects a broken run (any other code,
        or no requested DOI in the manifest) before recording. A missing CLI
        (``PaperforgeNotInstalled``) or a subprocess failure (e.g.
        ``subprocess.TimeoutExpired``) propagates as an exception.

        ``records`` holds only a manifest written by THIS call: paperforge
        rewrites ``manifest.csv`` on every run that reaches its batch, so a file
        whose mtime/size did not change is a leftover from an earlier call (this
        run exited before writing) and yields no records.

        Args:
            dois: DOIs to resolve (bare DOIs; paperforge also accepts files,
                but the adapter passes DOIs).
            output_dir: directory for ``manifest.csv``, ``pdfs/`` and sidecars
                (created if absent).
            **options: passthrough to :meth:`build_command` (source_order,
                licenses, require_known_license, no_metadata, overwrite, verbose).
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        cmd = self.build_command(list(dois), output_dir, **options)
        manifest_path = output_dir / "manifest.csv"
        before = _stat_signature(manifest_path)

        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=self.timeout,
        )

        written = _stat_signature(manifest_path)
        records = (
            self.parse_manifest(manifest_path)
            if written is not None and written != before
            else []
        )
        provenance = self._capture_provenance(cmd, proc.returncode)

        return AcquisitionResult(
            returncode=proc.returncode,
            output_dir=output_dir,
            manifest_path=manifest_path,
            records=records,
            provenance=provenance,
            stdout=proc.stdout or "",
            stderr=proc.stderr or "",
        )

    # -- provenance --------------------------------------------------------

    def _capture_provenance(self, cmd: list[str], returncode: int) -> dict[str, Any]:
        """Record which executable ran, why it was chosen, and the version it reports.

        ``pinned_sha`` is what pyproject.toml declares, kept for comparison; it is not
        evidence of what ran.
        """
        return {
            "tool": "paperforge",
            "tool_path": self.paperforge_bin,
            "tool_resolved_by": self.resolved_by,
            "tool_version": probe_tool_version(self.paperforge_bin),
            "pinned_sha": PINNED_SHA,
            "command": cmd,
            "returncode": returncode,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
