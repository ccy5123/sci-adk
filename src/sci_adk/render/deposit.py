"""
Deposit files (design/deposit-files.md): the protocol history and the declared data shipped
with the paper.

A reader holding only the paper bundle can check what the paper says about its protocol
and its data only if the files ship with it, or at least their checksums do. Every full
render writes, under ``paper/deposit/``:

  - ``protocol/protocol-v<N>.json`` -- each frozen version of the run's Spec, as the exact
    bytes the record keeps (``spec_history/spec.v<N>.json``; the current version is
    ``spec.json``), and ``protocol/amendment-v<N>.json`` -- each amendment receipt
    (``checkpoints/amendment-v<N>.json``), whose ``prior_spec_sha256`` is the SHA-256 of
    the version it replaced (D1);
  - ``data/<name>`` and ``inputs/<name>`` -- the declared data files that ship: study files
    (``recorded`` / ``derived``) and redistributed third-party files (``external``), copied
    from the sources the persisted declaration ``runs/<id>/deposit.json`` names (D3, D7);
  - ``record.tex`` -- a byte copy of the run's record ``runs/<id>/record.tex``, written after
    the record (with the bibliography below, the files render owns at the root of the
    folder, D13);
  - ``references.bib`` -- only when the record names ``\\bibliography{references}`` (its SI
    prose cites): a byte copy of the paper's ``paper/references.bib``, so the folder builds
    alone with bibtex (§7 Q12);
  - ``manifest.csv`` -- one row per file with its SHA-256, size, kind, the other files that
    state the same SHA-256, its citation, its terms and a description; a declared file that
    is cited, not shipped, is a row with no file; record identifiers never appear in it
    (D4). Its first line is a fixed marker by which render knows it wrote the file (D13).

A run whose persisted declaration withholds its protocol ships no protocol file; the
manifest still lists each one, with the SHA-256 of the record's file and the reason (D1).
The record ships either way: it prints the protocol files' times and checksums, the
hypotheses with their decision rules, and never the raw proposal.

The D5 checks are pure functions here: the bundle (:func:`deposit_bundle_problems`), the
declared data against the Evidence (:func:`deposit_data_problems`) and the paths the paper
names (:func:`deposit_name_problems`, :func:`package_name_problems`).

``record.tex`` carries a Protocol history section built from :func:`protocol_history` (each
file, its time, its SHA-256, and the protocol digest, D11), so the manifest's
``sha256_also_in`` names ``record.tex`` for every protocol row -- the copy in the bundle, which
``verify`` checks byte for byte against ``runs/<id>/record.tex``.

The package (D8) ships the protocol files under ``06_provenance/protocol/<id>/``, built from
``runs/<id>/`` directly, and the shipped data files under ``02_data/<id>/`` and
``05_inputs/<id>/``, copied from the per-run bundle, and lists them in
``06_provenance/deposit.csv`` under package paths (:func:`package_rows`); the assembler
writes them and the package gate checks them.

Everything here is READ-ONLY and deterministic: it reads the run directory (and, for the
checks, the per-run bundle) and returns values. The compiler is the only writer and applies
the D13 rules this module computes (:func:`prepare_deposit_write`). ``verify`` recomputes
every hash from bytes and rebuilds the expected manifest from ``runs/<id>/``.

Domain-neutral: nothing here reads what the files say beyond the protocol's version numbers,
times, receipts and checksums; a data file is bytes and a checksum.

The ``loop`` helpers (history path, receipt model, ``content_changes``) are imported inside
the functions: ``loop.compiler`` imports this module, and ``sci_adk.loop``'s package import
loads the compiler.
"""

from __future__ import annotations

import csv
import dataclasses
import hashlib
import io
import json
import os
import re
import stat
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from sci_adk.core.deposit import (
    DATA_FOLDER,
    INPUTS_FOLDER,
    ORIGIN_DERIVED,
    PLAIN_NAME_RE,
    DepositDeclarationError,
    DepositEntry,
    entry_source_path,
    load_deposit_declaration,
)

#: The bundle folder (under ``paper/``) and the three folders render owns inside it (D13);
#: the files it owns at the folder's root are :data:`RECORD_NAME` and
#: :data:`RECORD_BIB_NAME`.
DEPOSIT_DIR = "deposit"
PROTOCOL_DIR = "protocol"
DATA_DIR = DATA_FOLDER
INPUTS_DIR = INPUTS_FOLDER
OWNED_DIRS: Tuple[str, ...] = (PROTOCOL_DIR, DATA_DIR, INPUTS_DIR)

#: The per-run manifest, its first line and its columns (D4, D13).
MANIFEST_NAME = "manifest.csv"
MANIFEST_MARKER = "# Written with this paper; do not edit. Paths are relative to this folder."
MANIFEST_COLUMNS: Tuple[str, ...] = (
    "file", "sha256", "bytes", "kind", "sha256_also_in", "cite", "license", "description",
)
#: The package manifest (``06_provenance/deposit.csv``): the same columns plus the run id and
#: the Evidence id that holds the checksum, beside the record that resolves it (D4).
PACKAGE_MANIFEST_COLUMNS: Tuple[str, ...] = ("run", *MANIFEST_COLUMNS, "evidence")

#: The deposited record: ``paper/deposit/record.tex``, a byte copy of ``runs/<id>/record.tex``
#: written by every full render (the one file render owns at the root of ``paper/deposit/``,
#: D13), as named in the ``file`` and ``sha256_also_in`` columns, with its manifest kind and
#: fixed description (D4).
RECORD_NAME = "record.tex"
KIND_RECORD = "record"
RECORD_DESCRIPTION = (
    "the deterministic record of the study: every recorded item, its time and checksums"
)

#: The record's bibliography: a record whose SI prose cites ends with
#: ``\bibliography{references}`` (design/deposit-files.md §7 Q12), and the bundle then ships
#: ``paper/deposit/references.bib``, a byte copy of the paper's ``paper/references.bib``, so
#: ``paper/deposit/`` builds alone with bibtex; its manifest kind and fixed description (D4).
RECORD_BIB_NAME = "references.bib"
KIND_BIBLIOGRAPHY = "bibliography"
RECORD_BIB_DESCRIPTION = (
    "the references the record cites: a copy of the paper's bibliography"
)
# The record's closing lines when it names its bibliography, as ``si.render_si_latex`` writes
# them: the style line and the bibliography line, then ``\end{document}``, at the end of the
# file (trailing blank lines allowed; LF or CRLF). Matched at the end and not anywhere: a
# reproduction listing in the record may hold the same lines as code.
_RECORD_BIB_TAIL_RE = re.compile(
    rb"(?:\A|\n)\\bibliographystyle\{plainnat\}[ \t]*\r?\n"
    rb"\\bibliography\{references\}[ \t]*\r?\n"
    rb"(?:[ \t]*\r?\n)*\\end\{document\}\s*\Z"
)

#: The package's protocol folder (one ``<id>/`` per packaged run), its manifest and its
#: record, as paths relative to the package root (D8).
PACKAGE_PROTOCOL_DIR = "06_provenance/protocol"
PACKAGE_MANIFEST = "06_provenance/deposit.csv"
PACKAGE_RECORD = "06_provenance/record.tex"
#: The package's per-run folders for declared study data and redistributed third-party data
#: (one ``<id>/`` per run, rebuilt on every assembly, D8).
PACKAGE_DATA_DIR = "02_data"
PACKAGE_INPUTS_DIR = "05_inputs"

KIND_PROTOCOL = "protocol"
KIND_AMENDMENT = "amendment"

# A plain file name: [A-Za-z0-9._-]+ with no leading dot (D3), so never "." or "..".
_PLAIN_NAME_RE = PLAIN_NAME_RE

# Manifest row ranks (D4): rows with a path (every protocol row, every shipped data file)
# sort by that path; the data files not shipped come last, study data before third-party.
_RANK_PATH, _RANK_STUDY, _RANK_THIRD_PARTY = 0, 1, 2


def is_plain_name(name: str) -> bool:
    """Whether ``name`` is a plain file name: ``[A-Za-z0-9._-]+`` with no leading dot (D3)."""
    return _PLAIN_NAME_RE.fullmatch(name) is not None


class DepositRefused(ValueError):
    """A render that would write through a link, or over a file no render wrote (D13).

    Raised before anything under ``paper/`` is written; the message names the path.
    """


class ProtocolUnreadable(DepositRefused):
    """The run's protocol files cannot be read as the record keeps them (D1): a protocol
    file or its folder is a symbolic link or not a plain file, ``spec.json`` is not a Spec,
    or the version it states lies far past the files on disk.

    A :class:`DepositRefused`, so a render stops before writing anything under ``paper/``;
    ``verify`` and ``status`` report it. The message names the file.
    """


#: How many of versions 1..V (V: the version ``spec.json`` states) may have no file of the run
#: accounting for them. ``spec_history/spec.v<N>.json`` accounts for version N,
#: ``checkpoints/amendment-v<N>.json`` for versions N-1 and N, ``spec.json`` for V. Room for
#: a run amended before history files or receipts were kept (versions "not kept"); past it,
#: ``spec.json`` is not what the verbs wrote, and planning it would loop over versions no file
#: accounts for (a stray ``"version": 10000000`` hung verify and status).
VERSION_MARGIN = 10

_HISTORY_NAME_RE = re.compile(r"spec\.v([1-9][0-9]{0,8})\.json")
_RECEIPT_NAME_RE = re.compile(r"amendment-v([1-9][0-9]{0,8})\.json")


# --------------------------------------------------------------------------- #
# The protocol plan (D1)
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class ProtocolFile:
    """One protocol version or amendment receipt of the run, as the record keeps it.

    Attributes:
        name: the reader-facing name in the bundle (``protocol-v1.json``).
        kind: ``protocol`` or ``amendment``.
        version: the version it is (``protocol``) or produced (``amendment``).
        record_name: where the record keeps it, relative to ``runs/<id>/``.
        data: its exact bytes; ``None`` for a version whose file was not kept.
        description: the fixed manifest description (D4).
    """

    name: str
    kind: str
    version: int
    record_name: str
    data: Optional[bytes]
    description: str

    @property
    def kept(self) -> bool:
        return self.data is not None

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.data).hexdigest() if self.data is not None else ""

    @property
    def path(self) -> str:
        """The path relative to ``paper/deposit/`` it has, or would have when shipped."""
        return f"{PROTOCOL_DIR}/{self.name}"


@dataclass(frozen=True)
class ProtocolPlan:
    """The run's protocol history and what of it ships (D1).

    Attributes:
        spec_id: the run's Spec id.
        version: the current version V (``spec.json``).
        files: versions 1..V and every amendment receipt on disk, by bundle path.
        withheld_reason: the declaration's ``protocol_reason`` when the protocol is
            withheld; ``None`` when it ships (the default).
        license: the declaration's top-level ``license``, the terms the shipped protocol
            files take (D7); ``None`` when none is stated.
    """

    spec_id: str
    version: int
    files: Tuple[ProtocolFile, ...]
    withheld_reason: Optional[str] = None
    license: Optional[str] = None

    @property
    def withheld(self) -> bool:
        return self.withheld_reason is not None

    @property
    def shipped(self) -> Tuple[ProtocolFile, ...]:
        """The files this render copies into ``paper/deposit/protocol/``."""
        if self.withheld:
            return ()
        return tuple(f for f in self.files if f.kept)

    def targets(self) -> Dict[str, bytes]:
        """``{path under paper/deposit/: bytes}`` of every shipped file."""
        return {f.path: f.data for f in self.shipped if f.data is not None}


def receipt_record_name(version: int) -> str:
    """Where the record keeps the receipt of the amendment that produced ``version``."""
    return f"checkpoints/amendment-v{version}.json"


def _lstat(path: Path, label: str) -> Optional[os.stat_result]:
    """``os.lstat`` of a record path (never following a link); ``None`` when absent."""
    try:
        return os.lstat(path)
    except FileNotFoundError:
        return None
    except OSError as e:
        raise ProtocolUnreadable(f"{label} cannot be read ({e})") from e


def _check_record_folder(run_dir: Path, name: str) -> None:
    """Refuse a protocol folder of the run that is a symbolic link or not a folder."""
    label = f"runs/{run_dir.name}/{name}/"
    st = _lstat(run_dir / name, label)
    if st is None:
        return
    if stat.S_ISLNK(st.st_mode):
        raise ProtocolUnreadable(
            f"{label} is a symbolic link; the record's protocol files are read only from "
            "plain folders -- replace the link with the folder it points to"
        )
    if not stat.S_ISDIR(st.st_mode):
        raise ProtocolUnreadable(f"{label} is not a folder")


def _record_bytes(run_dir: Path, rel: str) -> Optional[bytes]:
    """The exact bytes of the run's record file ``rel``; ``None`` when there is none. Never
    read through a symbolic link: a link, or anything but a plain file, is refused."""
    label = f"runs/{run_dir.name}/{rel}"
    path = run_dir / rel
    st = _lstat(path, label)
    if st is None:
        return None
    if stat.S_ISLNK(st.st_mode):
        raise ProtocolUnreadable(
            f"{label} is a symbolic link; the record's protocol files are read only as plain "
            "files -- replace the link with the file it points to"
        )
    if not stat.S_ISREG(st.st_mode):
        raise ProtocolUnreadable(f"{label} is not a plain file")
    try:
        return path.read_bytes()
    except OSError as e:
        raise ProtocolUnreadable(f"{label} cannot be read ({e})") from e


def _numbers_on_disk(folder: Path, pattern: re.Pattern[str]) -> List[int]:
    """The version numbers of the files in ``folder`` whose names match ``pattern``."""
    if not folder.is_dir():
        return []
    out = []
    for p in folder.iterdir():
        match = pattern.fullmatch(p.name)
        if match:
            out.append(int(match.group(1)))
    return out


def _check_version_bound(run_dir: Path, version: int, history_dir: str) -> None:
    """Refuse a ``version`` with more than :data:`VERSION_MARGIN` of versions 1..``version``
    that no file of the run accounts for (a history file of that version, the receipt of
    the amendment that produced it or the one that replaced it, or ``spec.json`` itself) --
    so a stray number in ``spec.json`` fails at once instead of planning that many versions.
    """
    history = _numbers_on_disk(run_dir / history_dir, _HISTORY_NAME_RE)
    receipts = _numbers_on_disk(run_dir / "checkpoints", _RECEIPT_NAME_RE)
    accounted = {version} | set(history) | set(receipts) | {n - 1 for n in receipts}
    missing = version - len({n for n in accounted if 1 <= n <= version})
    if missing > VERSION_MARGIN:
        highest = max([1, *(n + 1 for n in history), *receipts])
        raise ProtocolUnreadable(
            f"runs/{run_dir.name}/spec.json says version {version}, but no file of the run "
            f"accounts for {missing} of versions 1 to {version} (at most {VERSION_MARGIN} may "
            f"lack one); its history files and amendment receipts reach version {highest}. "
            "spec.json is not what the amend verb wrote"
        )


def plan_protocol(run_dir: Path, declaration: Any = None) -> ProtocolPlan:
    """The run's protocol history, read from ``runs/<id>/`` (D1).

    ``declaration`` is the run's :class:`~sci_adk.core.deposit.DepositDeclaration` (or
    ``None``): it decides whether the protocol is withheld and which terms it takes.

    Every protocol file is read with ``lstat`` first and never through a symbolic link, and
    the version ``spec.json`` states is bounded by the files on disk
    (:data:`VERSION_MARGIN`).

    Raises:
        FileNotFoundError: the run has no ``spec.json``.
        ProtocolUnreadable: (a ``ValueError``) ``spec.json`` is not JSON with a positive
            integer ``version``; it, a history file, a receipt, or the ``spec_history/`` or
            ``checkpoints/`` folder is a symbolic link or not a plain file / folder; or the
            version lies more than :data:`VERSION_MARGIN` versions past the files on disk.
    """
    from sci_adk.loop.amend_spec import HISTORY_DIR

    run_dir = Path(run_dir)
    if run_dir.name in ("", ".", ".."):     # "." from inside the run: name it in messages
        run_dir = run_dir.resolve()
    for folder in (HISTORY_DIR, "checkpoints"):
        _check_record_folder(run_dir, folder)
    current = _record_bytes(run_dir, "spec.json")
    if current is None:
        raise FileNotFoundError(f"runs/{run_dir.name}/spec.json does not exist")
    try:
        payload = json.loads(current.decode("utf-8"))
        version = int(payload.get("version", 1))
        spec_id = str(payload.get("id") or run_dir.name)
    except (UnicodeDecodeError, ValueError, AttributeError, TypeError) as e:
        raise ProtocolUnreadable(
            f"runs/{run_dir.name}/spec.json is not a readable Spec ({e})") from e
    if version < 1:
        raise ProtocolUnreadable(f"runs/{run_dir.name}/spec.json has version {version}")
    _check_version_bound(run_dir, version, HISTORY_DIR)

    files: List[ProtocolFile] = []
    for n in range(1, version):
        record_name = f"{HISTORY_DIR}/spec.v{n}.json"
        data = _record_bytes(run_dir, record_name)
        description = (
            f"protocol, version {n}, replaced by version {n + 1}" if data is not None
            else f"protocol, version {n}; file not kept"
        )
        files.append(ProtocolFile(
            f"protocol-v{n}.json", KIND_PROTOCOL, n, record_name, data, description))
    files.append(ProtocolFile(
        f"protocol-v{version}.json", KIND_PROTOCOL, version, "spec.json", current,
        f"protocol, version {version} (current)"))
    for n in range(2, version + 1):
        record_name = receipt_record_name(n)
        data = _record_bytes(run_dir, record_name)
        if data is not None:
            files.append(ProtocolFile(
                f"amendment-v{n}.json", KIND_AMENDMENT, n, record_name, data,
                f"amendment that produced version {n}"))
    files.sort(key=lambda f: f.path)
    return ProtocolPlan(
        spec_id=spec_id,
        version=version,
        files=tuple(files),
        withheld_reason=getattr(declaration, "protocol_reason", None),
        license=getattr(declaration, "license", None),
    )


def plan_run_protocol(run_dir: Path) -> ProtocolPlan:
    """:func:`plan_protocol` with the run's persisted declaration applied (D1, D2): the
    protocol half of :func:`plan_run_deposit`, which also validates the declared sources.

    Raises:
        FileNotFoundError: the run has no ``spec.json``.
        ValueError: ``spec.json`` is not a readable Spec, or ``runs/<id>/deposit.json`` is
            invalid (:class:`~sci_adk.core.deposit.DepositDeclarationError`).
    """
    return plan_run_deposit(run_dir)[0]


# --------------------------------------------------------------------------- #
# Declared data (D3, D7)
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class DataFile:
    """One declared data file, its source read at plan time.

    Attributes:
        entry: the validated declaration entry.
        sha256: of its ``source``'s bytes.
        size: its ``source``'s length in bytes.
        data: the exact bytes of its ``source`` when the entry ships (render copies them);
            ``None`` for an entry that does not ship, whose source is hashed in chunks and
            never held whole (a third-party workbook can run to megabytes).
    """

    entry: DepositEntry
    sha256: str
    size: int
    data: Optional[bytes] = None

    @property
    def would_be_path(self) -> str:
        """``data/<name>`` or ``inputs/<name>`` (relative to ``paper/deposit/``) when the
        entry states a name, shipped or not; else ``""``."""
        return f"{self.entry.folder}/{self.entry.name}" if self.entry.name else ""

    @property
    def path(self) -> str:
        """The path relative to ``paper/deposit/`` of a shipped file; ``""`` otherwise."""
        return self.would_be_path if self.entry.ships else ""


@dataclass(frozen=True)
class DataPlan:
    """The run's declared data files and which of them ship (D3, D7).

    Attributes:
        license: the declaration's top-level ``license`` (taken by a shipped study file with
            no cited source and no license of its own); ``None`` when none is stated.
        files: every declared entry with its source bytes, in declaration order.
    """

    license: Optional[str] = None
    files: Tuple[DataFile, ...] = ()

    @property
    def shipped(self) -> Tuple[DataFile, ...]:
        return tuple(f for f in self.files if f.entry.ships)

    def targets(self) -> Dict[str, bytes]:
        """``{path under paper/deposit/: bytes}`` of every shipped data file."""
        return {f.path: f.data for f in self.shipped if f.data is not None}


#: The chunk an unshipped source is hashed in.
_HASH_CHUNK = 1 << 20


def _read_source(entry: DepositEntry, path: Path, source: str) -> DataFile:
    """Hash ``path`` -- holding its bytes only when the entry ships. An ``OSError`` (a file
    that exists but cannot be read) is a declaration error naming the entry."""
    try:
        if entry.ships:
            data = path.read_bytes()
            return DataFile(entry, hashlib.sha256(data).hexdigest(), len(data), data)
        digest = hashlib.sha256()
        size = 0
        with open(path, "rb") as handle:
            while True:
                chunk = handle.read(_HASH_CHUNK)
                if not chunk:
                    break
                digest.update(chunk)
                size += len(chunk)
        return DataFile(entry, digest.hexdigest(), size)
    except OSError as e:
        raise DepositDeclarationError(
            f"{source}: files[{entry.index}]: 'source' {entry.source!r} is not readable ({e})"
        ) from e


def plan_data(run_dir: Path, declaration: Any = None) -> DataPlan:
    """The declared data files of the run, each source read from disk (D3).

    ``declaration`` is the run's validated declaration (or ``None``: no data).

    Raises:
        DepositDeclarationError: a source is missing, resolves outside the workspace, is a
            protocol file, lies under ``runs/<id>/paper/`` or in a run's record
            (:func:`entry_source_path`), or exists but cannot be read.
    """
    if declaration is None:
        return DataPlan()
    source = f"runs/{Path(run_dir).name}/deposit.json"
    return DataPlan(
        license=declaration.license,
        files=tuple(
            _read_source(entry, entry_source_path(entry, run_dir, source=source), source)
            for entry in declaration.files
        ),
    )


def plan_run_deposit(run_dir: Path) -> Tuple[ProtocolPlan, DataPlan]:
    """The run's protocol plan and data plan with its persisted declaration applied (D1-D3).

    For callers that hold no Spec of their own (the package assembler and gate): the
    declaration is validated against the Spec id ``spec.json`` states.

    Raises:
        FileNotFoundError: the run has no ``spec.json``.
        ValueError: ``spec.json`` is not a readable Spec, or ``runs/<id>/deposit.json`` is
            invalid (:class:`~sci_adk.core.deposit.DepositDeclarationError`).
    """
    plan = plan_protocol(run_dir)
    declaration = load_deposit_declaration(Path(run_dir), plan.spec_id)
    if declaration is None:
        return plan, DataPlan()
    plan = dataclasses.replace(
        plan, withheld_reason=declaration.protocol_reason, license=declaration.license)
    return plan, plan_data(run_dir, declaration)


# --------------------------------------------------------------------------- #
# The protocol digest (D11)
# --------------------------------------------------------------------------- #

def digest_of_files(files: Mapping[str, bytes]) -> str:
    """The SHA-256 of the text ``sha256sum`` prints for ``files`` under their names.

    One line ``<64 lowercase hex><two spaces><name>\\n`` per file, names in byte order --
    what ``cd deposit/protocol && LC_ALL=C sha256sum $(LC_ALL=C ls) | sha256sum`` computes.
    """
    listing = "".join(
        f"{hashlib.sha256(files[name]).hexdigest()}  {name}\n" for name in sorted(files)
    )
    return hashlib.sha256(listing.encode("utf-8")).hexdigest()


# @MX:ANCHOR: [AUTO] the protocol digest -- render, status, verify, record.tex and the
#   package (run_index.csv, its record.tex) all print this value.
# @MX:REASON: [AUTO] D11: a reader recomputes it from the bundle with standard tools and an
#   author deposits it with a third party; every place must print the same bytes-derived value,
#   withheld or not, and it must not move when Evidence is appended.
def protocol_digest(plan: ProtocolPlan) -> str:
    """The protocol digest of the run (D11): every kept version and receipt under its bundle
    name, from the record's exact bytes -- the same value whether the protocol ships or not."""
    return digest_of_files({f.name: f.data for f in plan.files if f.data is not None})


# --------------------------------------------------------------------------- #
# Manifest rows and text (D4)
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class ManifestRow:
    """One manifest row (D4). ``rank`` and ``key`` order the rows (:func:`_row_order`);
    ``evidence`` is package-only."""

    file: str
    sha256: str
    size: str
    kind: str
    sha256_also_in: str = ""
    cite: str = ""
    license: str = ""
    description: str = ""
    key: str = ""
    evidence: str = ""
    rank: int = _RANK_PATH

    def cells(self) -> Tuple[str, ...]:
        return (self.file, self.sha256, self.size, self.kind, self.sha256_also_in,
                self.cite, self.license, self.description)


def _row_order(row: ManifestRow) -> Tuple[Any, ...]:
    """D4 order: rows with a path by that path in byte order (a withheld or not-kept protocol
    row by the path its file would have); then the data files not shipped, study data before
    third-party data, each group by ``sha256``, then ``description``."""
    if row.rank == _RANK_PATH:
        return (row.rank, row.key, "", "", row.cells())
    return (row.rank, "", row.sha256, row.description, row.cells())


def holds_sha256(text: str, sha256: str) -> bool:
    """Whether ``text`` carries ``sha256`` as a whole 64-hex token, in any letter case."""
    if not sha256:
        return False
    return re.search(
        rf"(?<![0-9A-Fa-f]){re.escape(sha256)}(?![0-9A-Fa-f])", text, re.IGNORECASE
    ) is not None


def protocol_rows(
    plan: ProtocolPlan,
    record_text: Optional[str],
    *,
    root: str = PROTOCOL_DIR,
    record_name: str = RECORD_NAME,
) -> List[ManifestRow]:
    """The manifest rows of the protocol history, in path order (D4).

    ``sha256_also_in`` names the other files a reader can open that state the row's
    SHA-256: the shipped protocol files (for a replaced version, its amendment receipt) and
    the record (``record_text``, named ``record_name``) wherever it prints the value.

    ``root`` is the folder the files sit in, as written in the ``file`` column: per run
    ``protocol`` (relative to ``paper/deposit/``); in the package
    ``06_provenance/protocol/<id>`` with ``record_name`` ``06_provenance/record.tex``
    (relative to the package root, D8).
    """
    shipped = {f.name for f in plan.shipped}
    shipped_text = {
        f.name: f.data.decode("latin-1") for f in plan.shipped if f.data is not None
    }
    suffix = f"; withheld: {plan.withheld_reason}" if plan.withheld else ""
    rows: List[ManifestRow] = []
    for f in plan.files:
        is_shipped = f.name in shipped
        path = f"{root}/{f.name}"
        also: List[str] = []
        if f.kept:
            also.extend(
                f"{root}/{name}" for name, text in shipped_text.items()
                if name != f.name and holds_sha256(text, f.sha256)
            )
            if record_text and holds_sha256(record_text, f.sha256):
                also.append(record_name)
        rows.append(ManifestRow(
            file=path if is_shipped else "",
            sha256=f.sha256,
            size=str(len(f.data)) if f.data is not None else "",
            kind=f.kind,
            sha256_also_in=";".join(sorted(also)),
            license=(plan.license or "") if is_shipped else "",
            description=f.description + suffix,
            key=path,
        ))
    return sorted(rows, key=lambda r: r.key)


def _shipped_protocol_texts(plan: ProtocolPlan, root: str) -> Dict[str, str]:
    """``{path: text}`` of the protocol files a reader of the bundle can open (none when
    withheld), for ``sha256_also_in``."""
    return {f"{root}/{f.name}": f.data.decode("latin-1")
            for f in plan.shipped if f.data is not None}


def data_rows(
    data: DataPlan,
    *,
    roots: Mapping[str, str],
    also_texts: Mapping[str, str],
    record_text: Optional[str],
    record_name: str = RECORD_NAME,
) -> List[ManifestRow]:
    """The manifest rows of the declared data files (D4, D7).

    ``roots`` maps an entry's folder (``data`` / ``inputs``) to the folder its file has in the
    ``file`` column (per run the same; in the package ``02_data/<id>`` and ``05_inputs/<id>``).
    A file that is not shipped has an empty ``file``, the checksum of its source and "not
    redistributed". ``sha256_also_in`` names the files in ``also_texts`` (the shipped protocol
    files) and the record (``record_text``, named ``record_name``) that state the checksum --
    never for a ``derived`` file, which carries no integrity claim (D3).
    """
    rows: List[ManifestRow] = []
    for df in data.files:
        entry = df.entry
        sha = df.sha256
        also: List[str] = []
        if entry.origin != ORIGIN_DERIVED:
            also.extend(path for path, text in also_texts.items() if holds_sha256(text, sha))
            if record_text and holds_sha256(record_text, sha):
                also.append(record_name)
        if entry.ships:
            file_ = f"{roots[entry.folder]}/{entry.name}"
            rank = _RANK_PATH
        else:
            file_ = ""
            rank = _RANK_THIRD_PARTY if entry.external else _RANK_STUDY
        rows.append(ManifestRow(
            file=file_,
            sha256=sha,
            size=str(df.size),
            kind=entry.kind,
            sha256_also_in=";".join(sorted(also)),
            cite=";".join(entry.cite),
            license=entry.terms(data.license),
            description=entry.description,
            key=file_,
            evidence=(entry.evidence or "") if entry.origin != ORIGIN_DERIVED else "",
            rank=rank,
        ))
    return rows


def record_row(record: bytes, license: Optional[str]) -> ManifestRow:
    """The manifest row of the shipped record ``record.tex`` (D4): its SHA-256 and size, kind
    ``record``, the top-level ``license`` (a file the study produced), the fixed description.
    No other shipped file states its SHA-256, so ``sha256_also_in`` is empty."""
    return ManifestRow(
        file=RECORD_NAME,
        sha256=hashlib.sha256(record).hexdigest(),
        size=str(len(record)),
        kind=KIND_RECORD,
        license=license or "",
        description=RECORD_DESCRIPTION,
        key=RECORD_NAME,
    )


def record_bibliography(record: Optional[bytes]) -> Optional[str]:
    """The bibliography file the record names, as it ships beside the record copy
    (:data:`RECORD_BIB_NAME`), or ``None``: ``record`` (the bytes of
    ``runs/<id>/record.tex``) ends with ``\\bibliographystyle{plainnat}``,
    ``\\bibliography{references}`` and ``\\end{document}`` only when its SI prose cites
    (§7 Q12; :data:`_RECORD_BIB_TAIL_RE`). Those lines elsewhere -- in a reproduction listing
    -- do not count. PURE."""
    if record is None or _RECORD_BIB_TAIL_RE.search(record) is None:
        return None
    return RECORD_BIB_NAME


def record_bib_row(bib: bytes) -> ManifestRow:
    """The manifest row of the shipped record bibliography ``references.bib`` (D4): its
    SHA-256 and size, kind ``bibliography``, the fixed description. The file lists
    published references, not a file the study produced, so it takes no top-level
    ``license``; no other shipped file states its SHA-256."""
    return ManifestRow(
        file=RECORD_BIB_NAME,
        sha256=hashlib.sha256(bib).hexdigest(),
        size=str(len(bib)),
        kind=KIND_BIBLIOGRAPHY,
        description=RECORD_BIB_DESCRIPTION,
        key=RECORD_BIB_NAME,
    )


# @MX:ANCHOR: [AUTO] the per-run manifest rows -- render writes them, verify's plan check and
#   the CLI's summary read them; package_rows is their package twin.
# @MX:REASON: [AUTO] D4: render and verify must compute the same rows from runs/<id>/ and the
#   persisted declaration, in one total order, or every re-render reads as stale.
def deposit_rows(
    plan: ProtocolPlan,
    data: Optional[DataPlan],
    record: Optional[bytes],
    record_bib: Optional[bytes] = None,
) -> List[ManifestRow]:
    """Every row of the per-run ``paper/deposit/manifest.csv`` in D4 order: the protocol
    history (:func:`protocol_rows`), the declared data (:func:`data_rows`), the record and,
    when it ships, the record's bibliography (``record_bib``, the bytes of
    ``paper/references.bib``; :func:`record_bib_row`).

    ``record`` is the bytes of ``runs/<id>/record.tex``, which ships as
    ``paper/deposit/record.tex``: it gets its row (:func:`record_row`) and is searched for
    ``sha256_also_in``, so the column names ``record.tex`` only when the bundle holds it.
    ``None`` (no ``runs/<id>/record.tex``): no record row, and no cell names it.
    """
    # latin-1 maps every byte to one character, so a 64-hex token is found as it is in bytes
    record_text = record.decode("latin-1") if record is not None else None
    rows = list(protocol_rows(plan, record_text))
    if data is not None:
        rows.extend(data_rows(
            data,
            roots={DATA_DIR: DATA_DIR, INPUTS_DIR: INPUTS_DIR},
            also_texts=_shipped_protocol_texts(plan, PROTOCOL_DIR),
            record_text=record_text,
        ))
    if record is not None:
        rows.append(record_row(record, plan.license))
    if record_bib is not None:
        rows.append(record_bib_row(record_bib))
    return sorted(rows, key=_row_order)


def manifest_text(rows: Sequence[ManifestRow]) -> str:
    """The per-run ``paper/deposit/manifest.csv``: the marker line, the header, the rows."""
    buf = io.StringIO()
    buf.write(MANIFEST_MARKER + "\n")
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(MANIFEST_COLUMNS)
    for row in rows:
        writer.writerow(row.cells())
    return buf.getvalue()


def package_manifest_text(rows: Sequence[Tuple[str, ManifestRow]]) -> str:
    """The package ``06_provenance/deposit.csv``: ``(run id, row)`` pairs as given, with the
    ``run`` and ``evidence`` columns and no marker (the package rebuilds its folders whole)."""
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(PACKAGE_MANIFEST_COLUMNS)
    for run_id, row in rows:
        writer.writerow((run_id, *row.cells(), row.evidence))
    return buf.getvalue()


def package_protocol_root(run_id: str) -> str:
    """Where the package ships a run's protocol files, relative to the package root (D8)."""
    return f"{PACKAGE_PROTOCOL_DIR}/{run_id}"


def package_data_root(folder: str, run_id: str) -> str:
    """Where the package ships a run's declared files of ``folder`` (``data`` / ``inputs``),
    relative to the package root (D8)."""
    return f"{PACKAGE_INPUTS_DIR if folder == INPUTS_DIR else PACKAGE_DATA_DIR}/{run_id}"


def package_rows(
    plans: Sequence[Tuple[str, ProtocolPlan]],
    record_text: Optional[str],
    data: Optional[Mapping[str, DataPlan]] = None,
) -> List[Tuple[str, ManifestRow]]:
    """The ``06_provenance/deposit.csv`` rows of the packaged runs (D4, D8): each run's
    :func:`protocol_rows` and :func:`data_rows` under package paths, ``sha256_also_in``
    searched in the run's protocol copies and the package's ``06_provenance/record.tex``
    (``record_text``), in the D4 order across runs (ties among unshipped rows broken by run
    id). ``data`` maps a run id to its data plan (absent: no declared data)."""
    out: List[Tuple[str, ManifestRow]] = []
    for run_id, plan in plans:
        root = package_protocol_root(run_id)
        out.extend(
            (run_id, row) for row in protocol_rows(
                plan, record_text, root=root, record_name=PACKAGE_RECORD)
        )
        run_data = (data or {}).get(run_id)
        if run_data is not None:
            out.extend((run_id, row) for row in data_rows(
                run_data,
                roots={folder: package_data_root(folder, run_id)
                       for folder in (DATA_DIR, INPUTS_DIR)},
                also_texts=_shipped_protocol_texts(plan, root),
                record_text=record_text,
                record_name=PACKAGE_RECORD,
            ))
    return sorted(out, key=lambda pair: (*_row_order(pair[1])[:4], pair[0],
                                         _row_order(pair[1])[4]))


def package_manifest_records(text: str) -> Optional[List[Dict[str, str]]]:
    """The rows of a package ``deposit.csv`` text, or ``None`` when its header is not the D4
    package header or a row has the wrong number of cells."""
    reader = csv.reader(io.StringIO(text))
    try:
        header = next(reader)
    except (StopIteration, csv.Error):
        return None
    if tuple(header) != PACKAGE_MANIFEST_COLUMNS:
        return None
    out: List[Dict[str, str]] = []
    try:
        for cells in reader:
            if not cells:
                continue
            if len(cells) != len(PACKAGE_MANIFEST_COLUMNS):
                return None
            out.append(dict(zip(PACKAGE_MANIFEST_COLUMNS, cells)))
    except csv.Error:
        return None
    return out


def package_manifest_differences(actual: str, expected: str) -> List[str]:
    """Why the package ``deposit.csv`` text ``actual`` is not ``expected`` -- one line per
    row only one of them holds, else a line about order or formatting."""
    act = [tuple(r[c] for c in PACKAGE_MANIFEST_COLUMNS)
           for r in (package_manifest_records(actual) or [])]
    exp = [tuple(r[c] for c in PACKAGE_MANIFEST_COLUMNS)
           for r in (package_manifest_records(expected) or [])]

    def label(row: Sequence[str]) -> str:
        run_id, file_, sha, description = row[0], row[1], row[2], row[8]
        where = file_ or "(no file)"
        tail = f", SHA-256 {sha}" if sha and not file_ else ""
        return f"run '{run_id}': {where}, {description}{tail}"

    out = [f"{PACKAGE_MANIFEST} lacks the row the record calls for: {label(row)}"
           for row in exp if row not in act]
    out.extend(f"{PACKAGE_MANIFEST} has a row the record does not call for: {label(row)}"
               for row in act if row not in exp)
    if not out:
        out.append(f"{PACKAGE_MANIFEST} is not the text the package writes (row order or "
                   "formatting)")
    return out


def _manifest_records(text: str) -> Optional[List[Dict[str, str]]]:
    """The rows of a manifest's text (marker line included), or ``None`` when the header is
    not the D4 header or a row has the wrong number of cells."""
    lines = text.split("\n", 1)
    body = lines[1] if len(lines) > 1 else ""
    reader = csv.reader(io.StringIO(body))
    try:
        header = next(reader)
    except StopIteration:
        return None
    except csv.Error:
        return None
    if tuple(header) != MANIFEST_COLUMNS:
        return None
    out: List[Dict[str, str]] = []
    try:
        for cells in reader:
            if not cells:
                continue
            if len(cells) != len(MANIFEST_COLUMNS):
                return None
            out.append(dict(zip(MANIFEST_COLUMNS, cells)))
    except csv.Error:
        return None
    return out


def _starts_with_marker(raw: bytes) -> bool:
    return raw.split(b"\n", 1)[0].rstrip(b"\r") == MANIFEST_MARKER.encode("utf-8")


def unlisted_paths(deposit_dir: Path, listed: Any) -> List[str]:
    """The files (and links) under ``paper/deposit/``, other than the manifest, that
    ``listed`` (manifest ``file`` cells) does not name, by path -- what the inventory fails
    and what render warns about when it leaves one in place (D5, D13)."""
    deposit_dir = Path(deposit_dir)
    if not deposit_dir.is_dir():
        return []
    out: List[str] = []
    for path in sorted(deposit_dir.rglob("*")):
        if path.is_dir() and not path.is_symlink():
            continue
        rel = path.relative_to(deposit_dir).as_posix()
        if rel != MANIFEST_NAME and rel not in listed:
            out.append(rel)
    return out


def _cell_problem(deposit_dir: Path, cell: str) -> Optional[str]:
    """Why a manifest ``file`` cell is not one render could have written, or ``None`` (D13):
    ``record.tex``, ``references.bib``, or ``protocol/``, ``data/`` or ``inputs/`` followed by
    a plain file name, resolving inside ``paper/deposit/`` with no symbolic link on the way."""
    if cell in (RECORD_NAME, RECORD_BIB_NAME):
        return "it is a symbolic link" if (deposit_dir / cell).is_symlink() else None
    parts = cell.split("/")
    if len(parts) != 2 or parts[0] not in OWNED_DIRS or not _PLAIN_NAME_RE.fullmatch(parts[1]):
        return ("not record.tex, references.bib, or protocol/, data/ or inputs/ followed by "
                "a plain file name")
    folder = deposit_dir / parts[0]
    if folder.is_symlink():
        return f"its folder paper/deposit/{parts[0]} is a symbolic link"
    target = folder / parts[1]
    if target.is_symlink():
        return "it is a symbolic link"
    try:
        target.resolve().relative_to(deposit_dir.resolve())
    except (OSError, ValueError):
        return "it resolves outside paper/deposit/"
    return None


# --------------------------------------------------------------------------- #
# Writing under the D13 rules: what render may write and remove
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class DepositWrite:
    """What a render writes and removes under ``paper/deposit/`` (computed, not applied).

    Attributes:
        deposit_dir: ``paper/deposit/``.
        writes: ``{path: bytes}`` to write -- the path holds nothing, or a file an earlier
            render listed.
        unchanged: paths that already hold exactly the bytes render writes (they count as
            written; nothing changes).
        removals: render-written paths this render does not write, whose bytes still have
            the SHA-256 the trusted previous manifest lists -- never a path that is the same
            file as a target (a case-only rename on a case-insensitive file system).
        warnings: one line per untrusted manifest cell, unreadable manifest, or listed file
            whose bytes changed (left in place).
        left: the listed files whose bytes changed, left in place (each has its warning).
    """

    deposit_dir: Path
    writes: Dict[str, bytes]
    unchanged: Tuple[str, ...]
    removals: Tuple[str, ...]
    warnings: Tuple[str, ...]
    left: Tuple[str, ...] = ()


def _sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(_HASH_CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _same_file(a: Path, b: Path) -> bool:
    """Whether ``a`` and ``b`` name one file (on a case-insensitive file system, two
    spellings of one name do). A path that does not exist is not the same file; when the
    file system cannot tell, they count as the same, so nothing is removed."""
    try:
        return os.path.samefile(a, b)
    except FileNotFoundError:
        return False
    except OSError:
        return True


def _case_variants(rel: str, others: Any) -> List[str]:
    """The paths in ``others`` that differ from ``rel`` in letter case only."""
    return [o for o in others if o != rel and o.lower() == rel.lower()]


def _refuse_link(path: Path, label: str) -> None:
    if path.is_symlink():
        raise DepositRefused(
            f"{label} is a symbolic link; render never writes through a link -- replace it "
            "with a plain folder or file and render again"
        )


# @MX:WARN: [AUTO] Decides which files under paper/ a render may overwrite or delete.
# @MX:REASON: [AUTO] D13: a hand-edited or foreign manifest must never make render delete or
#   overwrite an author's file (e.g. paper/draft.tex). Only a manifest carrying the marker
#   whose every cell is a plain name in an owned folder is trusted, and only unchanged bytes
#   are removed; widening either rule turns the manifest into a deletion list.
def prepare_deposit_write(paper_dir: Path, targets: Mapping[str, bytes]) -> DepositWrite:
    """Apply the D13 rules to ``targets`` (``{path under paper/deposit/: bytes}``).

    Read-only. Render stops (:class:`DepositRefused`) when ``paper/deposit/``, one of its
    three folders, the manifest or a target path is a symbolic link; when a target path
    holds other bytes and no trusted previous manifest lists it; and when a
    ``manifest.csv`` exists without the marker. A lost, unreadable-past-the-marker or
    untrusted manifest never blocks: nothing it lists is removed, and a target that already
    holds the bytes counts as written. A target is a file in one of the three folders, or
    ``record.tex`` (the record's copy) or ``references.bib`` (its bibliography's copy) at the
    root, the cells a trusted manifest may hold.
    """
    deposit_dir = Path(paper_dir) / DEPOSIT_DIR
    _refuse_link(deposit_dir, "paper/deposit")
    if deposit_dir.exists() and not deposit_dir.is_dir():
        raise DepositRefused("paper/deposit exists and is not a folder; move it away")
    for sub in OWNED_DIRS:
        folder = deposit_dir / sub
        _refuse_link(folder, f"paper/deposit/{sub}")
        if folder.exists() and not folder.is_dir():
            raise DepositRefused(f"paper/deposit/{sub} exists and is not a folder; move it away")

    warnings: List[str] = []
    listed: Dict[str, str] = {}
    manifest = deposit_dir / MANIFEST_NAME
    _refuse_link(manifest, f"paper/deposit/{MANIFEST_NAME}")
    if manifest.exists():
        if not manifest.is_file():
            raise DepositRefused(f"paper/deposit/{MANIFEST_NAME} is not a file; move it away")
        raw = manifest.read_bytes()
        if not _starts_with_marker(raw):
            raise DepositRefused(
                f"paper/deposit/{MANIFEST_NAME} was not written by a render (its first line is "
                "not the marker); move it away and render again"
            )
        try:
            records = _manifest_records(raw.decode("utf-8"))
        except UnicodeDecodeError:
            records = None
        if records is None:
            warnings.append(
                f"paper/deposit/{MANIFEST_NAME} could not be read past its first line; "
                "nothing it lists was removed"
            )
        else:
            bad: List[Tuple[str, str]] = []
            for record in records:
                reason = _cell_problem(deposit_dir, record["file"]) if record["file"] else None
                if reason:
                    bad.append((record["file"], reason))
            if bad:
                warnings.extend(
                    f"paper/deposit/{MANIFEST_NAME} is not trusted -- row file {cell!r}: "
                    f"{reason}; nothing it lists was removed"
                    for cell, reason in bad
                )
            else:
                listed = {r["file"]: r["sha256"] for r in records if r["file"]}

    writes: Dict[str, bytes] = {}
    unchanged: List[str] = []
    for rel, data in sorted(targets.items()):
        target = deposit_dir / rel
        _refuse_link(target, f"paper/deposit/{rel}")
        if target.exists():
            if not target.is_file():
                raise DepositRefused(f"paper/deposit/{rel} is not a file; move it away")
            if target.read_bytes() == data:
                unchanged.append(rel)
                continue
            # A listed path differing in letter case only that is this very file: the
            # case-insensitive file system shows the earlier render's file under the new name.
            renamed = any(_same_file(deposit_dir / v, target)
                          for v in _case_variants(rel, listed))
            if rel not in listed and not renamed:
                raise DepositRefused(
                    f"paper/deposit/{rel} exists with other content and no earlier render "
                    "listed it; move it away and render again"
                )
        writes[rel] = data

    removals: List[str] = []
    left: List[str] = []
    for rel, sha in sorted(listed.items()):
        if rel in targets:
            continue
        target = deposit_dir / rel
        if not target.is_file():
            continue
        # A case-only rename: on a case-insensitive file system the old name is the target
        # itself, and removing it would delete the file this render writes.
        if any(_same_file(target, deposit_dir / t) for t in _case_variants(rel, targets)):
            continue
        if _sha256_of(target) == sha:
            removals.append(rel)
        else:
            left.append(rel)
            warnings.append(
                f"paper/deposit/{rel} was written by an earlier render but its bytes changed "
                "since; it was left in place -- delete it, or restore it"
            )
    return DepositWrite(
        deposit_dir=deposit_dir, writes=writes, unchanged=tuple(unchanged),
        removals=tuple(removals), warnings=tuple(warnings), left=tuple(left),
    )


# --------------------------------------------------------------------------- #
# The D5 protocol checks
# --------------------------------------------------------------------------- #

def _time_of(value: Any) -> Optional[datetime]:
    """A recorded time parsed the way the Spec model parses ``created_at``; aware UTC."""
    from pydantic import TypeAdapter, ValidationError

    if value is None:
        return None
    try:
        parsed = TypeAdapter(datetime).validate_python(value)
    except ValidationError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


def _timestamp_id(value: Any) -> Optional[str]:
    """``prior_version_id`` as ``Spec.amend`` writes it from a ``created_at`` value."""
    from pydantic import TypeAdapter, ValidationError

    try:
        parsed = TypeAdapter(datetime).validate_python(value)
    except ValidationError:
        return None
    return str(parsed.timestamp())


def _version_payloads(plan: ProtocolPlan, fails: List[str]) -> Dict[int, dict]:
    out: Dict[int, dict] = {}
    for f in plan.files:
        if f.kind != KIND_PROTOCOL or f.data is None:
            continue
        try:
            payload = json.loads(f.data.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            fails.append(f"{f.record_name} is not readable JSON")
            continue
        if not isinstance(payload, dict):
            fails.append(f"{f.record_name} is not a JSON object")
            continue
        if payload.get("version") != f.version:
            fails.append(
                f"{f.record_name} says version {payload.get('version')!r}, not {f.version}")
        out[f.version] = payload
    return out


def protocol_record_problems(plan: ProtocolPlan) -> Tuple[List[str], List[str]]:
    """The record-side D5 comparisons among the run's own protocol files.

    These run whether the protocol ships or is withheld: each receipt's
    ``prior_spec_sha256`` against the SHA-256 of the history file it names (earlier
    protocols), each version's ``created_at`` against the next version's
    ``prior_version_id``, each receipt's ``rationale`` against the ``amendment_rationale``
    of the version it produced (amendments), and each receipt's version numbers.

    Returns ``(fails, advisories)``. A version not kept (no history file, and a receipt that
    records no checksum of it) and a missing receipt are advisories. A pass shows that the
    files agree with one another, nothing more: the earlier versions and the receipts are
    outside the record digest (D11).
    """
    from sci_adk.loop.amend_spec import AmendmentReceipt

    fails: List[str] = []
    notes: List[str] = []
    versions = {f.version: f for f in plan.files if f.kind == KIND_PROTOCOL}
    receipt_files = {f.version: f for f in plan.files if f.kind == KIND_AMENDMENT}
    payloads = _version_payloads(plan, fails)

    receipts: Dict[int, Any] = {}
    for n in range(2, plan.version + 1):
        name = receipt_record_name(n)
        rfile = receipt_files.get(n)
        if rfile is None or rfile.data is None:
            notes.append(
                f"protocol history: {name} does not exist, so the step from version {n - 1} "
                f"to version {n} cannot be checked"
            )
            continue
        try:
            receipt = AmendmentReceipt.model_validate_json(rfile.data)
        except ValueError as e:
            fails.append(f"{name} is not a readable amendment receipt ({str(e).splitlines()[0]})")
            continue
        if receipt.prior_version != n - 1 or receipt.new_version != n:
            fails.append(
                f"{name} records the step from version {receipt.prior_version} to version "
                f"{receipt.new_version}, not {n - 1} to {n}"
            )
        if receipt.spec_id != plan.spec_id:
            fails.append(f"{name} is for {receipt.spec_id!r}, not {plan.spec_id!r}")
        receipts[n] = receipt
        if n in payloads:
            stated = (payloads[n].get("amendment_rationale") or "").strip()
            if receipt.rationale.strip() != stated:
                fails.append(
                    f"{name}: its rationale differs from the amendment_rationale of version "
                    f"{n} ({versions[n].record_name})"
                )

    for n in range(1, plan.version):
        f = versions[n]
        receipt = receipts.get(n + 1)
        recorded = receipt.prior_spec_sha256 if receipt is not None else None
        rname = receipt_record_name(n + 1)
        if f.data is None:
            if recorded:
                fails.append(
                    f"{f.record_name} is missing, although {rname} records its SHA-256 "
                    f"{recorded}"
                )
            else:
                notes.append(
                    f"protocol history: version {n} was not kept ({f.record_name} does not "
                    "exist); the manifest lists it with no file"
                )
            continue
        if receipt is not None:
            if not recorded:
                notes.append(
                    f"protocol history: {rname} records no SHA-256 of version {n}, so "
                    f"{f.record_name} cannot be compared with it"
                )
            elif recorded.lower() != f.sha256:
                fails.append(
                    f"{f.record_name}: its SHA-256 {f.sha256} differs from the "
                    f"prior_spec_sha256 {recorded} in {rname}"
                )
        nxt = payloads.get(n + 1)
        if n in payloads and nxt is not None:
            expected = _timestamp_id(payloads[n].get("created_at"))
            if expected is None:
                fails.append(
                    f"{f.record_name}: created_at {payloads[n].get('created_at')!r} is not a "
                    "readable time"
                )
            elif nxt.get("prior_version_id") != expected:
                fails.append(
                    f"{versions[n + 1].record_name}: prior_version_id "
                    f"{nxt.get('prior_version_id')!r} is not version {n}'s created_at as a "
                    f"timestamp ({expected})"
                )
    return fails, notes


def _row_label(cells: Sequence[str]) -> str:
    file_, sha = cells[0], cells[1]
    where = file_ or "(no file)"
    return f"{where}, {cells[7]}" + (f", SHA-256 {sha}" if sha and not file_ else "")


def _plan_differences(actual: str, expected: str, run_name: str) -> List[str]:
    act = _manifest_records(actual)
    exp = _manifest_records(expected) or []
    act_rows = [tuple(r[c] for c in MANIFEST_COLUMNS) for r in (act or [])]
    exp_rows = [tuple(r[c] for c in MANIFEST_COLUMNS) for r in exp]
    out: List[str] = []
    for row in exp_rows:
        if row not in act_rows:
            out.append(
                f"paper/deposit/{MANIFEST_NAME} lacks the row runs/{run_name}/ calls for: "
                f"{_row_label(row)} -- re-render"
            )
    for row in act_rows:
        if row not in exp_rows:
            out.append(
                f"paper/deposit/{MANIFEST_NAME} has a row runs/{run_name}/ does not call for: "
                f"{_row_label(row)} -- re-render"
            )
    if not out:
        out.append(
            f"paper/deposit/{MANIFEST_NAME} is not the text render writes for runs/{run_name}/ "
            "(row order or formatting) -- re-render"
        )
    return out


def deposit_bundle_problems(
    paper_dir: Path,
    plan: ProtocolPlan,
    record_bytes: Optional[bytes],
    data: Optional[DataPlan] = None,
) -> List[str]:
    """The D5 checks on the per-run bundle ``paper/deposit/`` (every one a failure).

      - inventory: the manifest starts with the marker; every listed file exists under
        ``paper/deposit/`` with that SHA-256 and size; every file there is listed; every
        ``sha256_also_in`` target is a listed file the bundle holds;
      - plan: the manifest is the one ``runs/<id>/`` (its protocol files, its persisted
        declaration and the declared sources, ``data``) and ``runs/<id>/record.tex``
        (``record_bytes``, its bytes; ``None`` when absent) call for -- the render is not stale;
      - current protocol / earlier protocols / amendments (copies): each shipped file's
        bytes equal the record's file; each shipped data file's bytes equal its source;
      - record: ``paper/deposit/record.tex`` is byte-identical to ``runs/<id>/record.tex``;
      - record bibliography: when the record names ``\\bibliography{references}``,
        ``paper/deposit/references.bib`` is byte-identical to ``paper/references.bib`` (and
        listed, through the plan check).

    Every hash is recomputed from bytes; the manifest's ``sha256`` column is never trusted.
    """
    deposit_dir = Path(paper_dir) / DEPOSIT_DIR
    bib_name = record_bibliography(record_bytes)
    bib_source = Path(paper_dir) / bib_name if bib_name is not None else None
    record_bib = (
        bib_source.read_bytes()
        if bib_source is not None and bib_source.is_file() and not bib_source.is_symlink()
        else None
    )
    run_name = plan.spec_id
    problems: List[str] = []

    manifest = deposit_dir / MANIFEST_NAME
    text: Optional[str] = None
    records: List[Dict[str, str]] = []
    if manifest.is_symlink() or not manifest.is_file():
        problems.append(f"paper/deposit/{MANIFEST_NAME} is missing -- re-render")
    else:
        raw = manifest.read_bytes()
        if not _starts_with_marker(raw):
            problems.append(
                f"paper/deposit/{MANIFEST_NAME} does not start with the marker line: render "
                "did not write it"
            )
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            problems.append(f"paper/deposit/{MANIFEST_NAME} is not UTF-8 text")
        if text is not None:
            parsed = _manifest_records(text)
            if parsed is None:
                problems.append(
                    f"paper/deposit/{MANIFEST_NAME} does not have the columns "
                    f"{','.join(MANIFEST_COLUMNS)}"
                )
            else:
                records = parsed

    listed: Dict[str, Dict[str, str]] = {r["file"]: r for r in records if r["file"]}
    for rel, record in sorted(listed.items()):
        reason = _cell_problem(deposit_dir, rel)
        if reason:
            problems.append(f"paper/deposit/{MANIFEST_NAME} row file {rel!r}: {reason}")
            continue
        path = deposit_dir / rel
        if not path.is_file():
            problems.append(f"paper/deposit/{rel} is listed in the manifest but missing")
            continue
        held = path.read_bytes()
        actual = hashlib.sha256(held).hexdigest()
        if actual != record["sha256"]:
            problems.append(
                f"paper/deposit/{rel}: its SHA-256 {actual} differs from the manifest's "
                f"{record['sha256'] or '(empty)'}"
            )
        if str(len(held)) != record["bytes"]:
            problems.append(
                f"paper/deposit/{rel}: {len(held)} bytes, the manifest says "
                f"{record['bytes'] or '(empty)'}"
            )
    problems.extend(
        f"paper/deposit/{rel} is not in the manifest (left from an earlier render, or added "
        "by hand)" for rel in unlisted_paths(deposit_dir, listed)
    )
    for row in records:
        for target in (t for t in row["sha256_also_in"].split(";") if t):
            if target not in listed or not (deposit_dir / target).is_file():
                problems.append(
                    f"paper/deposit/{MANIFEST_NAME} row "
                    f"{_row_label(tuple(row[c] for c in MANIFEST_COLUMNS))}: "
                    f"sha256_also_in points to {target}, which the bundle does not hold"
                )

    if text is not None:
        expected = manifest_text(deposit_rows(plan, data, record_bytes, record_bib))
        if text != expected:
            problems.extend(_plan_differences(text, expected, run_name))

    copy = deposit_dir / RECORD_NAME
    if record_bytes is None:
        problems.append(
            f"runs/{run_name}/{RECORD_NAME} is missing, so paper/deposit/{RECORD_NAME} cannot "
            "be checked against it -- re-render"
        )
    elif copy.is_symlink() or not copy.is_file():
        problems.append(
            f"paper/deposit/{RECORD_NAME} is missing (the record of the study; the run keeps "
            f"it as runs/{run_name}/{RECORD_NAME}) -- re-render"
        )
    elif copy.read_bytes() != record_bytes:
        problems.append(
            f"paper/deposit/{RECORD_NAME} differs from runs/{run_name}/{RECORD_NAME} -- "
            "re-render"
        )
    if bib_name is not None:
        bib_copy = deposit_dir / bib_name
        if record_bib is None:
            problems.append(
                f"paper/{bib_name} is missing, so paper/deposit/{bib_name} (the bibliography "
                f"{RECORD_NAME} names) cannot be checked against it -- re-render"
            )
        elif bib_copy.is_symlink() or not bib_copy.is_file():
            problems.append(
                f"paper/deposit/{bib_name} is missing (the bibliography {RECORD_NAME} names; "
                f"the paper keeps it as paper/{bib_name}) -- re-render"
            )
        elif bib_copy.read_bytes() != record_bib:
            problems.append(
                f"paper/deposit/{bib_name} differs from paper/{bib_name} -- re-render"
            )

    for f in plan.shipped:
        copy = deposit_dir / f.path
        if copy.is_symlink() or not copy.is_file():
            problems.append(
                f"paper/deposit/{f.path} is missing ({f.description}; the record keeps it as "
                f"{f.record_name}) -- re-render"
            )
        elif copy.read_bytes() != f.data:
            problems.append(
                f"paper/deposit/{f.path} differs from runs/{run_name}/{f.record_name} -- "
                "re-render"
            )
    for df in (data.shipped if data is not None else ()):
        copy = deposit_dir / df.path
        if copy.is_symlink() or not copy.is_file():
            problems.append(
                f"paper/deposit/{df.path} is missing ({df.entry.label}) -- re-render")
        elif copy.read_bytes() != df.data:
            problems.append(
                f"paper/deposit/{df.path} differs from its source {df.entry.source} -- "
                "re-render"
            )
    return problems


# --------------------------------------------------------------------------- #
# The D5 data checks (recorded, derived, external, cited not shipped, citations, terms)
# --------------------------------------------------------------------------- #

def _held_by(holders: Sequence[str]) -> str:
    if holders:
        return f"; it occurs in Evidence item(s) {', '.join(holders)}"
    return "; no Evidence item holds it"


def _cite_problems(entry: DepositEntry, keys: Optional[set], bib_name: str) -> List[str]:
    out: List[str] = []
    for key in entry.cite:
        if keys is None:
            out.append(f"{entry.label}: cite key {key!r} cannot be resolved: the paper has no "
                       f"{bib_name}")
        elif key not in keys:
            out.append(f"{entry.label}: cite key {key!r} is not in {bib_name}")
    return out


# @MX:ANCHOR: [AUTO] the D5 data checker -- render (Evidence it is given, as warnings), verify
#   (Evidence on disk, failures gate) and the package gate (per packaged run) all call it.
# @MX:REASON: [AUTO] D5: one pure checker so the three places cannot disagree on what binds a
#   declared file to the record; render must never read evidence/ itself (it checks the list
#   the paper and record.tex were rendered from).
def deposit_data_problems(
    plan: ProtocolPlan,
    data: DataPlan,
    evidence: Sequence[Any],
    bib_text: Optional[str],
    *,
    folder_of: Optional[Mapping[str, str]] = None,
    bib_name: str = "references.bib",
) -> Tuple[List[str], List[str]]:
    """The D5 checks on the declared data files, READ-ONLY and pure.

    Returns ``(fails, advisories)``:

      - recorded / external (fail): the file's SHA-256 occurs as a 64-hex token, in any
        letter case, in the serialized JSON of the named Evidence item; the message names
        the items that do hold it;
      - derived: listed as unchecked (advisory); a named item that does not exist fails; an
        item that holds its checksum gets the advice to declare it recorded;
      - citations (fail): every ``cite`` key resolves in ``bib_text`` (``references.bib``);
      - cited, not shipped (advisory): a study file holding cited values that lacks
        ``license``, ``redistribution`` or both, and third-party data that states one of
        the two (§7 Q9: it ships only with both), with its checksum and citation;
      - terms (advisory): every shipped file with a cited source, with its terms; and, with
        no top-level ``license``, one line saying the bundle's own files state no terms (the
        record ships with every bundle, so there is always one).

    ``evidence`` is the Evidence list to check against: render passes the list it rendered,
    ``verify`` the log on disk. ``folder_of`` maps ``data`` / ``inputs`` to the path prefix
    messages print (per run ``deposit/data`` and ``deposit/inputs``); ``bib_name`` is how the
    citation messages name the bibliography ``bib_text`` came from.
    """
    from sci_adk.render.pkgreqs_checks import bib_keys

    prefix = dict(folder_of or {DATA_DIR: f"{DEPOSIT_DIR}/{DATA_DIR}",
                                INPUTS_DIR: f"{DEPOSIT_DIR}/{INPUTS_DIR}"})
    keys = set(bib_keys(bib_text)) if bib_text is not None else None
    serialized = {ev.id: ev.model_dump_json() for ev in evidence}
    fails: List[str] = []
    notes: List[str] = []
    for df in data.files:
        entry = df.entry
        sha = df.sha256
        holders = sorted(i for i, text in serialized.items() if holds_sha256(text, sha))
        if entry.origin == ORIGIN_DERIVED:
            notes.append(
                f"{entry.label}: derived, so its bytes are unchecked -- nothing in the record "
                f"fixes them (SHA-256 {sha})"
            )
            if entry.evidence is not None and entry.evidence not in serialized:
                fails.append(
                    f"{entry.label}: declared with Evidence item {entry.evidence}, which the "
                    "record does not hold"
                )
            if holders:
                notes.append(
                    f"{entry.label}: its SHA-256 occurs in Evidence item(s) "
                    f"{', '.join(holders)}: declare it recorded"
                )
        elif entry.evidence not in serialized:
            fails.append(
                f"{entry.label}: declared against Evidence item {entry.evidence}, which the "
                f"record does not hold{_held_by(holders)}"
            )
        elif entry.evidence not in holders:
            fails.append(
                f"{entry.label}: its SHA-256 {sha} does not occur in Evidence item "
                f"{entry.evidence}{_held_by(holders)}"
            )
        fails.extend(_cite_problems(entry, keys, bib_name))
        if not entry.external and entry.cite and not entry.ships:
            notes.append(
                f"{entry.label}: cited, not shipped -- SHA-256 {sha}, cites "
                f"{', '.join(entry.cite)}; it lacks {' and '.join(entry.lacking)} (a file of "
                "the study holding values from a cited source ships only with both)"
            )
        elif entry.external and len(entry.lacking) == 1:
            # One term stated: likely meant to ship (it did before §7 Q9 was decided).
            notes.append(
                f"{entry.label}: third-party data, not redistributed -- SHA-256 {sha}, cites "
                f"{', '.join(entry.cite)}; it lacks {entry.lacking[0]} (third-party data "
                "ships only with both license and redistribution)"
            )
        if entry.ships and entry.cite:
            notes.append(
                f"terms: {prefix[entry.folder]}/{entry.name} (cites {', '.join(entry.cite)}): "
                f"{entry.terms(data.license)}"
            )
    # The record (record.tex) ships with every bundle and takes the top-level license, so the
    # bundle always holds a file that takes it.
    if plan.license is None and data.license is None:
        notes.append(
            f"terms: no top-level license is declared (runs/{plan.spec_id}/deposit.json), so "
            "the files this study produced that ship with the paper -- the record, the "
            "protocol files and every declared file with no cited source and no license of "
            "its own -- state no terms"
        )
    return fails, notes


# --------------------------------------------------------------------------- #
# The names check (D5, D8): the paths the paper names
# --------------------------------------------------------------------------- #

# \url{...}, \nolinkurl{...} and the URL argument of \href are not paths in the bundle.
_URL_MASK_RES: Tuple[re.Pattern[str], ...] = (
    re.compile(r"\\(?:url|nolinkurl)\s*\{[^{}]*\}"),
    re.compile(r"\\href\s*\{[^{}]*\}"),
)
# A path from deposit/, not preceded by a word character, "/" or "." (so
# "zenodo.org/deposit/1.json" and "my_deposit/x" are not read).
_DEPOSIT_PATH_RE = re.compile(r"(?<![\w/.])deposit/[A-Za-z0-9._/-]*")
# A bare protocol file name render generates (D1), in any letter case, with no word
# character, "/", "." or "-" before it and no word character after it.
_BARE_PROTOCOL_RE = re.compile(
    r"(?<![\w/.\-])(?:protocol|amendment)-v\d+\.json(?!\w)", re.IGNORECASE)
# A package path (D8): one of the three folders the deposit fills, same left boundary.
_PACKAGE_PATH_RE = re.compile(
    r"(?<![\w/.])(?:02_data|05_inputs|06_provenance)/[A-Za-z0-9._/-]*")
_TRAILING = ".,;:)"
_FILE_WITH_EXTENSION_RE = re.compile(r"[^./][^/]*\.[A-Za-z0-9]+")


def _normalised(tex: str) -> str:
    """The text the names check reads (D5): URLs masked, ``\\_`` read as ``_``."""
    for pattern in _URL_MASK_RES:
        tex = pattern.sub(" ", tex)
    return tex.replace("\\_", "_")


def _clean(path: str) -> str:
    return path.rstrip(_TRAILING)


def _names_a_file(path: str) -> bool:
    return _FILE_WITH_EXTENSION_RE.fullmatch(path.rsplit("/", 1)[-1]) is not None


def deposit_name_problems(
    docs: Mapping[str, str],
    plan: ProtocolPlan,
    data: Optional[DataPlan] = None,
    bibliography: Optional[str] = None,
) -> Tuple[List[str], List[str]]:
    """The names and pointed-to checks of the per-run paper (D5), PURE.

    ``docs`` maps a document name (``draft.tex``, ``si.tex``) to its text. Every path that,
    after normalisation (URLs masked, ``\\_`` as ``_``, trailing ``.``, ``,``, ``;``, ``:``,
    ``)`` dropped), starts with ``deposit/`` and ends in a file name with an extension must be
    ``deposit/`` + a manifest ``file`` (or ``deposit/manifest.csv``; ``deposit/record.tex``,
    the record, ships with every bundle; ``deposit/references.bib`` when ``bibliography``
    names it, :func:`record_bibliography`); every bare ``protocol-v<N>.json`` /
    ``amendment-v<N>.json`` must be exactly the name of a shipped protocol file. A withheld
    protocol file or a declared file that is not shipped fails with a message saying so.
    Matching is exact: file names are case-sensitive.

    Returns ``(fails, advisories)``; the advisory (pointed to) when neither document names a
    deposited file.
    """
    data = data if data is not None else DataPlan()
    held = ({f.path for f in plan.shipped} | {df.path for df in data.shipped}
            | {MANIFEST_NAME, RECORD_NAME} | ({bibliography} if bibliography else set()))
    withheld = {f.path for f in plan.files} if plan.withheld else set()
    unshipped = {df.would_be_path: df.entry for df in data.files
                 if not df.entry.ships and df.would_be_path}
    protocol_names = {f.name for f in plan.shipped}
    would_be = {f.name.lower() for f in plan.files}
    withheld_note = (f"the protocol is withheld ({plan.withheld_reason}): no protocol file "
                     "ships with the paper")
    fails: List[str] = []
    pointed = False
    for doc, tex in docs.items():
        text = _normalised(tex)
        for match in _DEPOSIT_PATH_RE.finditer(text):
            path = _clean(match.group(0))
            rel = path[len(f"{DEPOSIT_DIR}/"):]
            if not _names_a_file(rel):
                continue
            if rel in held:
                pointed = True
            elif rel in withheld:
                fails.append(f"{doc} names {path}, but {withheld_note}")
            elif rel in unshipped:
                entry = unshipped[rel]
                fails.append(
                    f"{doc} names {path}, but that declared file is not shipped "
                    f"({entry.not_shipped_reason()}); cite its source and give its checksum "
                    "instead"
                )
            else:
                near = sorted(h for h in held if h.lower() == rel.lower())
                hint = (f" (file names are case-sensitive: the bundle holds "
                        f"{DEPOSIT_DIR}/{near[0]})" if near else "")
                fails.append(f"{doc} names {path}, which the bundle does not hold{hint}")
        for match in _BARE_PROTOCOL_RE.finditer(text):
            token = match.group(0)
            if token in protocol_names:
                pointed = True
            elif plan.withheld and token.lower() in would_be:
                fails.append(f"{doc} names {token}, but {withheld_note}")
            else:
                shipped = ", ".join(sorted(protocol_names)) or "none"
                fails.append(
                    f"{doc} names {token}, which is not a protocol file shipped with the paper "
                    f"(they are: {shipped})"
                )
    advisories: List[str] = []
    if docs and not pointed:
        advisories.append(
            "pointed to: neither the paper nor the SI names a deposited file; the availability "
            "statement can name them by their bundle paths (deposit/manifest.csv lists every "
            "file)"
        )
    return fails, advisories


def package_name_problems(
    package_dir: Path,
    docs: Mapping[str, str],
    deposits: Sequence[Tuple[str, ProtocolPlan, DataPlan]],
) -> List[str]:
    """The package names check (D8), READ-ONLY: in ``main.tex`` / ``si.tex`` (``docs``) every
    path from ``02_data/``, ``05_inputs/`` or ``06_provenance/`` exists in the package (a path
    into the protocol folder of a run that withholds its protocol fails saying so); a per-run
    ``deposit/`` path fails, naming the package path its manifest row maps to; a bare protocol
    file name must be the name of a file under some ``06_provenance/protocol/<id>/``."""
    package_dir = Path(package_dir)
    withheld = {rid: plan.withheld_reason for rid, plan, _ in deposits if plan.withheld}
    mapped: Dict[str, List[str]] = {MANIFEST_NAME: [PACKAGE_MANIFEST]}
    for rid, plan, data in deposits:
        for f in plan.shipped:
            mapped.setdefault(f.path, []).append(f"{package_protocol_root(rid)}/{f.name}")
        for df in data.shipped:
            mapped.setdefault(df.path, []).append(
                f"{package_data_root(df.entry.folder, rid)}/{df.entry.name}")
    root = package_dir / PACKAGE_PROTOCOL_DIR
    protocol_names = (
        {p.name for p in root.glob("*/*") if p.is_file()} if root.is_dir() else set()
    )
    fails: List[str] = []
    for doc, tex in docs.items():
        text = _normalised(tex)
        for match in _PACKAGE_PATH_RE.finditer(text):
            path = _clean(match.group(0))
            parts = path.split("/")
            if ".." not in parts and (package_dir / path).exists():
                continue
            rid = parts[2] if path.startswith(f"{PACKAGE_PROTOCOL_DIR}/") and len(parts) > 2 \
                else None
            if rid in withheld:
                fails.append(
                    f"{doc} names {path}, but the protocol of run '{rid}' is withheld "
                    f"({withheld[rid]}): no protocol file of it ships with the package"
                )
            else:
                fails.append(f"{doc} names {path}, which the package does not hold")
        for match in _DEPOSIT_PATH_RE.finditer(text):
            path = _clean(match.group(0))
            rel = path[len(f"{DEPOSIT_DIR}/"):]
            if not _names_a_file(rel):
                continue
            targets = mapped.get(rel)
            where = (f"in the package it is {' or '.join(targets)}" if targets
                     else "the package holds no such file")
            fails.append(f"{doc} names {path}, a path of a per-run paper; {where}")
        for match in _BARE_PROTOCOL_RE.finditer(text):
            token = match.group(0)
            if token in protocol_names:
                continue
            runs = sorted(rid for rid, plan, _ in deposits if plan.withheld
                          and token.lower() in {f.name.lower() for f in plan.files})
            if runs:
                fails.append(
                    f"{doc} names {token}, but the protocol of run(s) {', '.join(runs)} is "
                    "withheld: no such file ships with the package"
                )
            else:
                fails.append(
                    f"{doc} names {token}, which is the name of no file under "
                    f"{PACKAGE_PROTOCOL_DIR}/<run>/"
                )
    return fails


def withheld_advisory(reason: str) -> str:
    """The ``verify`` advisory for a run that withholds its protocol (D5)."""
    return (
        f"protocol withheld ({reason}): readers cannot check the protocol or what the paper "
        "says about it, such as when it was written; the manifest lists the SHA-256 of each "
        "withheld file"
    )


def _prior_checksum(receipt: ProtocolFile) -> str:
    """The ``prior_spec_sha256`` a receipt records, or ``""``."""
    try:
        value = json.loads((receipt.data or b"").decode("utf-8")).get("prior_spec_sha256")
    except (UnicodeDecodeError, ValueError, AttributeError):
        return ""
    return value if isinstance(value, str) else ""


def _history_coverage(plan: ProtocolPlan) -> Tuple[List[int], List[str]]:
    """Which steps from version n to n+1 the earlier-protocols check compared in full -- both
    versions kept and the receipt of n+1 recording the SHA-256 of version n -- and, in
    version order, why the others were not."""
    versions = {f.version: f for f in plan.files if f.kind == KIND_PROTOCOL}
    receipts = {f.version: f for f in plan.files if f.kind == KIND_AMENDMENT and f.kept}
    compared: List[int] = []
    gaps: List[str] = []
    for n in range(1, plan.version + 1):
        if not versions[n].kept:
            gaps.append(f"version {n} was not kept")
        if n == 1:
            continue
        receipt = receipts.get(n)
        if receipt is None:
            gaps.append(f"{receipt_record_name(n)} does not exist")
        elif not _prior_checksum(receipt):
            gaps.append(f"{receipt_record_name(n)} records no SHA-256 of version {n - 1}")
        elif versions[n - 1].kept and versions[n].kept:
            compared.append(n - 1)
    return compared, gaps


def protocol_history_line(plan: ProtocolPlan) -> str:
    """The pass line of the earlier-protocols check for an amended run (D5): "consistent",
    never "verified", and why. When a version was not kept, or a receipt is missing or
    records no checksum, the line says the history was partly compared and names the steps
    it compared and the gaps."""
    tail = ("the earlier versions and the receipts are outside the record digest, so this "
            "shows agreement, not that they were never rewritten")
    compared, gaps = _history_coverage(plan)
    if not gaps:
        receipts = sum(1 for f in plan.files if f.kind == KIND_AMENDMENT)
        return (
            f"protocol history: consistent -- versions 1 to {plan.version} and {receipts} "
            f"amendment receipt(s) agree with one another; {tail}"
        )
    steps = [f"from version {n} to {n + 1}" for n in compared]
    if not steps:
        agreed = "no step from one version to the next could be compared in full"
    elif len(steps) == 1:
        agreed = f"the step {steps[0]} agrees with its receipt"
    else:
        agreed = (f"the steps {', '.join(steps[:-1])} and {steps[-1]} agree with their "
                  "receipts")
    return (
        f"protocol history: partly compared -- of versions 1 to {plan.version}, {agreed}; not "
        f"compared in full: {'; '.join(gaps)}; {tail}"
    )


# --------------------------------------------------------------------------- #
# The times advisory (D12)
# --------------------------------------------------------------------------- #

def _fmt(t: Optional[datetime]) -> str:
    if t is None:
        return "time unknown"
    return t.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _utc(t: datetime) -> datetime:
    return t if t.tzinfo is not None else t.replace(tzinfo=timezone.utc)


def time_label(t: datetime) -> str:
    """A recorded time as ``record.tex`` and the times advisory print it: UTC, to the
    second (``2026-10-08T10:03:39Z``); a time without a zone is read as UTC."""
    return _fmt(_utc(t))


def _from_timestamp_id(value: Any) -> Optional[datetime]:
    try:
        return datetime.fromtimestamp(float(value), tz=timezone.utc)
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def _protocol_times(
    plan: ProtocolPlan, payloads: Mapping[int, dict]
) -> Tuple[Dict[int, Optional[datetime]], Dict[int, Optional[datetime]]]:
    """The recorded time of each version (its ``created_at``; for a version not kept, the
    next version's ``prior_version_id``) and of each amendment receipt (its
    ``recorded_at``). Every one comes from a local clock (D12)."""
    times: Dict[int, Optional[datetime]] = {}
    for n in range(1, plan.version + 1):
        t = _time_of(payloads[n].get("created_at")) if n in payloads else None
        if t is None and n + 1 in payloads:
            t = _from_timestamp_id(payloads[n + 1].get("prior_version_id"))
        times[n] = t
    receipt_times: Dict[int, Optional[datetime]] = {}
    for f in plan.files:
        if f.kind == KIND_AMENDMENT and f.data is not None:
            try:
                receipt_times[f.version] = _time_of(json.loads(f.data).get("recorded_at"))
            except (ValueError, AttributeError):
                receipt_times[f.version] = None
    return times, receipt_times


@dataclass(frozen=True)
class HistoryEntry:
    """One line of the Protocol history section of ``record.tex`` (D11).

    Attributes:
        name: the bundle name (``protocol-v1.json``).
        description: the fixed manifest description, without the withheld note (D4).
        time_label: ``created <time>`` (a version) or ``recorded <time>`` (a receipt).
        sha256: of the file's bytes; ``""`` for a version whose file was not kept.
    """

    name: str
    description: str
    time_label: str
    sha256: str


def protocol_history(plan: ProtocolPlan) -> List[HistoryEntry]:
    """The run's protocol files in the order they were written -- version 1, then each
    amendment receipt followed by the version it produced -- with their recorded times and
    checksums (D11). The same whether the protocol ships or is withheld."""
    scratch: List[str] = []
    payloads = _version_payloads(plan, scratch)
    times, receipt_times = _protocol_times(plan, payloads)
    versions = {f.version: f for f in plan.files if f.kind == KIND_PROTOCOL}
    receipts = {f.version: f for f in plan.files if f.kind == KIND_AMENDMENT}
    out: List[HistoryEntry] = []
    for n in range(1, plan.version + 1):
        receipt = receipts.get(n)
        if receipt is not None:
            out.append(HistoryEntry(
                receipt.name, receipt.description,
                f"recorded {_fmt(receipt_times.get(n))}", receipt.sha256))
        f = versions[n]
        out.append(HistoryEntry(f.name, f.description, f"created {_fmt(times[n])}", f.sha256))
    return out


def _touches(path: str, hyp_id: str) -> bool:
    return path.startswith((f"hypotheses[{hyp_id}].", f"hypotheses[{hyp_id}]:")) or (
        path.startswith(("method.", "method:", "method["))
    )


def times_advisory(plan: ProtocolPlan, evidence: Sequence[Any]) -> str:
    """The D12 advisory: the recorded times beside one another, and the items to look at.

    Line 1, the time of each protocol version and amendment; line 2, the earliest Evidence
    item and the earliest one bearing on a hypothesis; then, for each pair of consecutive
    versions, the items recorded between them that bear on no hypothesis; one line per
    version not kept; and one flag line per item created before protocol version 1, or
    bearing on a hypothesis h and created before the version h depends on -- the earliest
    k such that ``hypotheses[h]`` and ``method`` are unchanged from version k through the
    current one (``content_changes``). Every time comes from a local clock; nothing here
    checks one (D12). Continuation lines are indented four spaces.
    """
    from sci_adk.core.spec import Spec
    from sci_adk.loop.amend_spec import content_changes

    V = plan.version
    scratch: List[str] = []
    payloads = _version_payloads(plan, scratch)
    specs: Dict[int, Spec] = {}
    for n, payload in payloads.items():
        try:
            specs[n] = Spec.model_validate(payload)
        except ValueError:
            continue
    versions = {f.version: f for f in plan.files if f.kind == KIND_PROTOCOL}
    times, receipt_times = _protocol_times(plan, payloads)

    parts = [f"protocol v1 {_fmt(times[1])}"]
    for n in range(2, V + 1):
        if receipt_times.get(n) is not None:
            parts.append(f"amendment v{n} {_fmt(receipt_times[n])}")
        else:
            parts.append(f"protocol v{n} {_fmt(times[n])}")
    lines = ["times (local clocks, not witnessed): " + "; ".join(parts)]

    current = specs.get(V)
    hyp_ids = [h.id for h in current.hypotheses] if current is not None else [
        h.get("id") for h in payloads.get(V, {}).get("hypotheses", []) if isinstance(h, dict)
    ]
    hyp_set = set(hyp_ids)
    items = sorted(evidence, key=lambda ev: _utc(ev.created_at))

    def targets(ev: Any) -> List[str]:
        return list(dict.fromkeys(b.target_id for b in ev.bears_on if b.target_id in hyp_set))

    bearing = [ev for ev in items if targets(ev)]
    second = [
        f"earliest Evidence {_fmt(_utc(items[0].created_at))} ({items[0].kind.value})"
        if items else "no Evidence recorded",
        f"earliest bearing on a hypothesis {_fmt(_utc(bearing[0].created_at))}"
        if bearing else "nothing recorded bears on a hypothesis",
    ]
    lines.append("; ".join(second))

    for k in range(1, V):
        start, end = times[k], times[k + 1]
        if start is None or end is None:
            continue
        between = [
            ev for ev in items
            if start <= _utc(ev.created_at) < end and not targets(ev)
        ]
        if not between:
            continue
        counts = Counter(ev.kind.value for ev in between)
        first_seen: Dict[str, int] = {}
        for i, ev in enumerate(between):
            first_seen.setdefault(ev.kind.value, i)
        ordered = sorted(counts, key=lambda kind: (-counts[kind], first_seen[kind]))
        lines.append(
            f"{len(between)} item(s) recorded between v{k} and v{k + 1} bear on no hypothesis "
            f"({', '.join(f'{kind} {counts[kind]}' for kind in ordered)})"
        )

    for n in range(1, V):
        if not versions[n].kept:
            lines.append(
                f"version {n} was not kept: its content is unknown, so every hypothesis "
                f"counts as changed at version {n + 1}"
            )

    depends: Dict[str, int] = {}
    for h in hyp_ids:
        version_needed = 1
        for j in range(1, V):
            a, b = specs.get(j), specs.get(j + 1)
            if a is None or b is None or any(_touches(p, h) for p in content_changes(a, b)):
                version_needed = j + 1
        depends[h] = version_needed

    first_version = times[1]
    for ev in items:
        created = _utc(ev.created_at)
        if first_version is not None and created < first_version:
            lines.append(
                f"flagged: {ev.id} ({ev.kind.value}) created {_fmt(created)}, before protocol "
                f"v1 ({_fmt(first_version)})"
            )
            continue
        for h in targets(ev):
            k = depends[h]
            needed = times[k]
            if needed is not None and created < needed:
                lines.append(
                    f"flagged: {ev.id} ({ev.kind.value}, bears on {h}) created "
                    f"{_fmt(created)}, before protocol v{k} ({_fmt(needed)}), the version "
                    f"{h} depends on"
                )
    return "\n    ".join(lines)


__all__ = [
    "DATA_DIR",
    "DEPOSIT_DIR",
    "INPUTS_DIR",
    "KIND_AMENDMENT",
    "KIND_BIBLIOGRAPHY",
    "KIND_PROTOCOL",
    "KIND_RECORD",
    "MANIFEST_COLUMNS",
    "MANIFEST_MARKER",
    "MANIFEST_NAME",
    "OWNED_DIRS",
    "PACKAGE_DATA_DIR",
    "PACKAGE_INPUTS_DIR",
    "PACKAGE_MANIFEST",
    "PACKAGE_MANIFEST_COLUMNS",
    "PACKAGE_PROTOCOL_DIR",
    "PACKAGE_RECORD",
    "PROTOCOL_DIR",
    "RECORD_BIB_DESCRIPTION",
    "RECORD_BIB_NAME",
    "RECORD_DESCRIPTION",
    "RECORD_NAME",
    "VERSION_MARGIN",
    "DataFile",
    "DataPlan",
    "DepositRefused",
    "ProtocolUnreadable",
    "DepositWrite",
    "HistoryEntry",
    "ManifestRow",
    "ProtocolFile",
    "ProtocolPlan",
    "data_rows",
    "deposit_bundle_problems",
    "deposit_data_problems",
    "deposit_name_problems",
    "deposit_rows",
    "digest_of_files",
    "holds_sha256",
    "is_plain_name",
    "manifest_text",
    "package_manifest_differences",
    "package_manifest_records",
    "package_data_root",
    "package_manifest_text",
    "package_name_problems",
    "package_protocol_root",
    "package_rows",
    "plan_data",
    "plan_protocol",
    "plan_run_deposit",
    "plan_run_protocol",
    "prepare_deposit_write",
    "protocol_digest",
    "protocol_history",
    "protocol_history_line",
    "protocol_record_problems",
    "protocol_rows",
    "receipt_record_name",
    "record_bib_row",
    "record_bibliography",
    "record_row",
    "time_label",
    "times_advisory",
    "unlisted_paths",
    "withheld_advisory",
]
