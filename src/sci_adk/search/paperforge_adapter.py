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
"""

from __future__ import annotations

import csv
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from importlib import metadata as _ilmd
from pathlib import Path
from typing import Any, Optional, Sequence

# The git SHA paperforge is pinned to (pyproject.toml [tools]). Recorded in
# provenance so a run is traceable to an exact tool version, not "whatever was
# installed". Keep in sync with pyproject.toml.
PINNED_SHA = "2cec69b5c9e3cdd518463a24f67cf713ff3f0d9e"

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
    """Raised when the paperforge CLI cannot be located on PATH."""


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
    ) -> None:
        """
        Args:
            paperforge_bin: path to the ``paperforge`` executable. Defaults to
                whatever ``shutil.which`` finds on PATH (the entry point
                installed by ``pip install -e ".[tools]"``).
            email: contact email for the Unpaywall/OpenAlex polite pool. When
                None, paperforge falls back to ``$UNPAYWALL_EMAIL`` and, if that
                is also unset, skips Unpaywall (weaker results).
            timeout: subprocess timeout in seconds (a batch can be slow).
        """
        self.paperforge_bin = paperforge_bin or shutil.which("paperforge")
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
                "paperforge CLI not found on PATH; install it with "
                'pip install -e ".[tools]" (pins ccy5123/paperforge@'
                f"{PINNED_SHA[:7]})"
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

        A non-zero return code is NOT an error: ``EXIT_SOME_FAILED`` means some
        DOIs had no downloadable OA PDF -- a valid, recordable outcome (a null
        result is still a result). The per-DOI verdicts are in
        ``result.records``; inspect ``result.succeeded`` / ``result.failed``.
        Only a missing CLI (``PaperforgeNotInstalled``) or a subprocess failure
        (e.g. ``subprocess.TimeoutExpired``) propagates as an exception.

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

        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=self.timeout,
        )

        manifest_path = output_dir / "manifest.csv"
        records = self.parse_manifest(manifest_path)
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
        """Record the exact tool version and command for reproducibility."""
        return {
            "tool": "paperforge",
            "pinned_sha": PINNED_SHA,
            "installed_version": self._installed_version(),
            "tool_path": self.paperforge_bin,
            "command": cmd,
            "returncode": returncode,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    @staticmethod
    def _installed_version() -> Optional[str]:
        """The installed paperforge package version, or None if unavailable."""
        try:
            return _ilmd.version("paperforge")
        except _ilmd.PackageNotFoundError:
            return None
