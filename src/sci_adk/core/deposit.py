"""
The deposit declaration (design/deposit-files.md D2, D3): ``runs/<id>/deposit.json``.

The author's statement of what ships with the paper beyond what render ships by default.
It lives in the run directory, beside ``numbers.json`` and ``declarations.json``, so a render
never clobbers it; ``render``, ``verify`` and ``package`` all read it from there. A render
given ``--deposit <json>`` validates that file and copies its bytes here (D2).

Top-level keys, exactly: ``spec_id`` (required, the run's Spec id), ``license`` (the terms of
the files the study produced), ``protocol`` and ``protocol_reason`` (the switch that
withholds the protocol history, D1), ``files`` (the declared data entries; absent = ``[]``).

Entry keys, exactly: ``source``, ``name``, ``origin`` (``recorded`` / ``derived`` /
``external``), ``evidence``, ``cite``, ``license``, ``redistribution``, ``description``.
Which entries ship is decided by these fields alone (D3, D7):

  - ``recorded`` / ``derived`` with an empty ``cite``: ships (to ``paper/deposit/data/``);
  - ``recorded`` / ``derived`` with a non-empty ``cite``: cited, not shipped, unless it
    states both ``license`` and ``redistribution``;
  - ``external``: ships (to ``paper/deposit/inputs/``) only when it states both ``license``
    and ``redistribution`` (§7 Q9: the same two-field rule as a cited study file).

Not frozen, not part of the record: the file is outside ``record_digest`` and the protocol
digest, so setting or clearing the switch changes neither (D2).
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, List, Optional, Tuple

#: The persisted declaration's name inside ``runs/<id>/``.
DEPOSIT_FILE = "deposit.json"

#: The one accepted value of the ``protocol`` key.
PROTOCOL_WITHHELD = "withheld"

#: The three origins of a declared data file (D3).
ORIGIN_RECORDED = "recorded"
ORIGIN_DERIVED = "derived"
ORIGIN_EXTERNAL = "external"
ORIGINS: Tuple[str, ...] = (ORIGIN_RECORDED, ORIGIN_DERIVED, ORIGIN_EXTERNAL)

#: The one accepted value of an entry's ``redistribution`` key (D3).
REDISTRIBUTION_ASSERTED = "author-asserted"

#: The manifest's ``kind`` values for declared data (D4).
KIND_STUDY_DATA = "study data"
KIND_THIRD_PARTY_DATA = "third-party data"

#: The manifest's ``license`` cell for a data file that is cited, not shipped (D4).
NOT_REDISTRIBUTED = "not redistributed"
#: How the manifest states ``redistribution: "author-asserted"`` (D4).
REDISTRIBUTION_TERMS = "redistribution asserted by the authors"

#: The bundle folders a shipped entry lands in (under ``paper/deposit/``, D13).
DATA_FOLDER = "data"
INPUTS_FOLDER = "inputs"

#: Names the package generates or may generate in a per-run data folder, compared
#: case-insensitively; rejected in every mode so a per-run declaration is valid for the
#: package (D3, D8).
RESERVED_NAMES: Tuple[str, ...] = (
    "README.md", "claims.csv", "claims_all.csv", "deposit.csv", "manifest.csv",
)

_TOP_LEVEL_KEYS = ("spec_id", "license", "protocol", "protocol_reason", "files")
_ENTRY_KEYS = (
    "source", "name", "origin", "evidence", "cite", "license", "redistribution",
    "description",
)

#: A plain file name: ``[A-Za-z0-9._-]+`` with no leading dot (D3), so never ``.`` or ``..``.
PLAIN_NAME_RE = re.compile(r"[A-Za-z0-9_-][A-Za-z0-9._-]*")

# A name Windows reserves for a device, with or without an extension: the part before the
# first dot is CON, PRN, AUX, NUL, COM0-COM9 or LPT0-LPT9, in any letter case. A bundle
# unpacked there cannot hold a file of that name.
_WINDOWS_DEVICE_RE = re.compile(r"(?:con|prn|aux|nul|com[0-9]|lpt[0-9])(?:\..*)?",
                                re.IGNORECASE)

# Every character str.splitlines() breaks a line at: a "one line" value holds none of them.
_LINE_BREAKS = frozenset("\n\r\x0b\x0c\x1c\x1d\x1e\x85\u2028\u2029")


def windows_name_problem(name: str) -> Optional[str]:
    """Why a Windows file system would refuse or alter the file name ``name`` (a reserved
    device name, with or without an extension, or a name ending in ``.`` or a space), or
    ``None``."""
    if _WINDOWS_DEVICE_RE.fullmatch(name):
        return "a device name Windows reserves (CON, PRN, AUX, NUL, COM0-9, LPT0-9)"
    if name.endswith((".", " ")):
        return "it ends in '.' or a space, which Windows drops"
    return None

# A bib key as the manifest's ``cite`` cell carries it (joined by ``;``).
_CITE_KEY_RE = re.compile(r"[^\s,;{}]+")


class DepositDeclarationError(ValueError):
    """A deposit declaration that cannot be used; the message names the key at fault."""


@dataclass(frozen=True)
class DepositEntry:
    """One validated data entry of a deposit declaration (D3).

    Attributes:
        index: its position in ``files`` (load errors and messages name it).
        source: the relative path it is read from (run dir first, then the workspace).
        origin: ``recorded``, ``derived`` or ``external``.
        description: one line, for the manifest.
        name: the plain file name it ships under; ``None`` for an entry that does not ship
            and states none.
        evidence: the Evidence id that holds its checksum (or, for ``derived``, describes
            the step that produced it); ``None`` when not given.
        cite: the bib keys of the sources its values come from.
        license: the terms the deposited file itself is distributed under.
        redistribution: ``"author-asserted"`` or ``None``.
    """

    index: int
    source: str
    origin: str
    description: str
    name: Optional[str] = None
    evidence: Optional[str] = None
    cite: Tuple[str, ...] = ()
    license: Optional[str] = None
    redistribution: Optional[str] = None

    @property
    def external(self) -> bool:
        return self.origin == ORIGIN_EXTERNAL

    @property
    def ships(self) -> bool:
        """Whether render copies the file into the bundle (D3 "Which entries ship"): a study
        file with an empty ``cite`` always; third-party data and a study file holding cited
        values only when the entry states both ``license`` and ``redistribution``."""
        if not self.external and not self.cite:
            return True
        return self.license is not None and self.redistribution is not None

    @property
    def folder(self) -> str:
        """``inputs`` for third-party data, ``data`` for study data (D13)."""
        return INPUTS_FOLDER if self.external else DATA_FOLDER

    @property
    def kind(self) -> str:
        """The manifest's ``kind`` (D4)."""
        return KIND_THIRD_PARTY_DATA if self.external else KIND_STUDY_DATA

    @property
    def lacking(self) -> Tuple[str, ...]:
        """For an entry that does not ship, the one(s) of ``license`` and ``redistribution``
        whose absence keeps it out. ``()`` for an entry that ships."""
        if self.ships:
            return ()
        missing = []
        if self.license is None:
            missing.append("license")
        if self.redistribution is None:
            missing.append("redistribution")
        return tuple(missing)

    def terms(self, top_license: Optional[str]) -> str:
        """The manifest's ``license`` cell (D4): for a file that ships, its own ``license``,
        the redistribution statement, both joined by ``; ``, or the top-level ``license`` a
        study file with no cited source takes; for one that does not, "not redistributed"."""
        if not self.ships:
            return NOT_REDISTRIBUTED
        parts = []
        own = self.license
        if own is None and not self.external and not self.cite:
            own = top_license
        if own is not None:
            parts.append(own)
        if self.redistribution is not None:
            parts.append(REDISTRIBUTION_TERMS)
        return "; ".join(parts)

    def not_shipped_reason(self) -> str:
        """Why this entry is not shipped, in a reader's words (render prints it, D2)."""
        if self.external:
            return (f"third-party data, not redistributed: it lacks "
                    f"{' and '.join(self.lacking)}")
        return (f"cited, not shipped: it holds values from {', '.join(self.cite)} and "
                f"lacks {' and '.join(self.lacking)}")

    @property
    def label(self) -> str:
        """How messages refer to the entry."""
        return f"declared file {self.source}"


@dataclass(frozen=True)
class DepositDeclaration:
    """A validated deposit declaration.

    Attributes:
        spec_id: the run's Spec id.
        license: the terms of the files the study produced (the protocol files and every
            data entry with an empty ``cite``), or ``None`` when none is stated.
        protocol_reason: the one-line reason the protocol history is withheld; ``None``
            when the protocol ships (the default).
        files: the declared data entries, in declaration order.
    """

    spec_id: str
    license: Optional[str] = None
    protocol_reason: Optional[str] = None
    files: Tuple[DepositEntry, ...] = ()

    @property
    def withheld(self) -> bool:
        """Whether this run withholds its protocol history."""
        return self.protocol_reason is not None


def _one_line(value: Any, key: str, source: str) -> str:
    if not isinstance(value, str):
        raise DepositDeclarationError(f"{source}: '{key}' must be a string")
    if any(c in _LINE_BREAKS for c in value):
        raise DepositDeclarationError(
            f"{source}: '{key}' must be one line (no line break, including U+2028, U+2029, "
            "U+0085, vertical tab, form feed and U+001C-U+001E)")
    if not value.strip():
        raise DepositDeclarationError(f"{source}: '{key}' must not be empty")
    return value.strip()


def _reader_text(value: str, key: str, source: str) -> str:
    """Refuse text that reaches the manifest a reader receives and fails the paper
    vocabulary check (D3, D4). Imported here: core does not depend on render."""
    from sci_adk.render.paper import check_paper_tool_vocabulary

    flagged = check_paper_tool_vocabulary(value)
    if flagged:
        raise DepositDeclarationError(
            f"{source}: '{key}' fails the paper vocabulary check ({', '.join(flagged)}); it "
            "is printed in the manifest a reader receives"
        )
    return value


def _relative_source(value: Any, where: str) -> str:
    """A relative path with no ``..`` part (D3); the file system is not read here."""
    text = _one_line(value, "source", where)
    posix, windows = PurePosixPath(text), PureWindowsPath(text)
    if posix.is_absolute() or windows.is_absolute() or windows.drive or text.startswith(
            ("/", "\\")):
        raise DepositDeclarationError(
            f"{where}: 'source' {text!r} is an absolute path; give it relative to the run "
            "directory or the workspace"
        )
    if ".." in re.split(r"[\\/]", text):
        raise DepositDeclarationError(f"{where}: 'source' {text!r} contains '..'")
    return text


def _parse_entry(raw: Any, index: int, source: str) -> DepositEntry:
    where = f"{source}: files[{index}]"
    if not isinstance(raw, dict):
        raise DepositDeclarationError(f"{where}: must be an object")
    unknown = [k for k in raw if k not in _ENTRY_KEYS]
    if unknown:
        raise DepositDeclarationError(
            f"{where}: unknown key(s) {', '.join(repr(k) for k in unknown)}; the keys are "
            f"{', '.join(_ENTRY_KEYS)}"
        )
    if "source" not in raw:
        raise DepositDeclarationError(f"{where}: 'source' is required")
    src = _relative_source(raw["source"], where)

    origin = raw.get("origin")
    if origin not in ORIGINS:
        raise DepositDeclarationError(
            f"{where}: 'origin' must be one of {', '.join(ORIGINS)}, not {origin!r}")

    if "description" not in raw:
        raise DepositDeclarationError(f"{where}: 'description' (one line) is required")
    description = _reader_text(_one_line(raw["description"], "description", where),
                               "description", where)

    name = raw.get("name")
    if name is not None:
        if not isinstance(name, str) or not PLAIN_NAME_RE.fullmatch(name):
            raise DepositDeclarationError(
                f"{where}: 'name' {name!r} is not a plain file name ([A-Za-z0-9._-], no "
                "leading dot, no folder)"
            )
        _reader_text(name, "name", where)
        problem = windows_name_problem(name)
        if problem:
            raise DepositDeclarationError(
                f"{where}: 'name' {name!r} cannot be a file name on Windows: {problem}")
        if name.lower() in {r.lower() for r in RESERVED_NAMES}:
            raise DepositDeclarationError(
                f"{where}: 'name' {name!r} is reserved (the package generates "
                f"{', '.join(RESERVED_NAMES)} in a run's data folder)"
            )

    evidence = raw.get("evidence")
    if evidence is not None:
        evidence = _one_line(evidence, "evidence", where)
    if evidence is None and origin in (ORIGIN_RECORDED, ORIGIN_EXTERNAL):
        raise DepositDeclarationError(
            f"{where}: a {origin} entry needs 'evidence', the id of the Evidence item that "
            "holds its checksum"
        )

    cite = raw.get("cite", [])
    if not isinstance(cite, list) or not all(
            isinstance(k, str) and _CITE_KEY_RE.fullmatch(k) for k in cite):
        raise DepositDeclarationError(
            f"{where}: 'cite' must be a list of bib keys (no spaces, commas or semicolons)")
    for key in cite:
        _reader_text(key, "cite", where)
    if origin == ORIGIN_EXTERNAL and not cite:
        raise DepositDeclarationError(
            f"{where}: an external entry needs 'cite', the bib keys of its source")

    license_ = raw.get("license")
    if license_ is not None:
        license_ = _reader_text(_one_line(license_, "license", where), "license", where)

    redistribution = raw.get("redistribution")
    if redistribution is not None and redistribution != REDISTRIBUTION_ASSERTED:
        raise DepositDeclarationError(
            f"{where}: 'redistribution' must be {REDISTRIBUTION_ASSERTED!r} or absent, not "
            f"{redistribution!r}"
        )

    entry = DepositEntry(
        index=index, source=src, origin=origin, description=description, name=name,
        evidence=evidence, cite=tuple(cite), license=license_, redistribution=redistribution,
    )
    if entry.ships and entry.name is None:
        raise DepositDeclarationError(
            f"{where}: this entry ships (to paper/deposit/{entry.folder}/), so it needs a "
            "'name'"
        )
    return entry


def parse_deposit_declaration(
    payload: Any, spec_id: str, *, source: str = DEPOSIT_FILE
) -> DepositDeclaration:
    """Validate a decoded declaration against the run's Spec id (D3). Reads no file: the
    sources are checked by :func:`entry_source_path` (which :func:`load_deposit_declaration`
    and :func:`read_deposit_declaration` call).

    Raises:
        DepositDeclarationError: an unknown key, a missing or different ``spec_id``, a
            ``protocol`` other than ``"withheld"``, a ``protocol_reason`` that is missing
            when withheld, present otherwise, not one line, blank, or flagged by the paper
            vocabulary check; a ``files`` that is not a list; an entry that breaks a D3 rule
            (its index is named); two shipped names in one folder that differ at most in
            letter case.
    """
    if not isinstance(payload, dict):
        raise DepositDeclarationError(f"{source}: must be a JSON object")
    unknown = [k for k in payload if k not in _TOP_LEVEL_KEYS]
    if unknown:
        raise DepositDeclarationError(
            f"{source}: unknown key(s) {', '.join(repr(k) for k in unknown)}; the keys are "
            f"{', '.join(_TOP_LEVEL_KEYS)}"
        )
    if "spec_id" not in payload:
        raise DepositDeclarationError(f"{source}: 'spec_id' is required")
    if payload["spec_id"] != spec_id:
        raise DepositDeclarationError(
            f"{source}: 'spec_id' is {payload['spec_id']!r}, but this run's Spec id is "
            f"{spec_id!r}"
        )

    license_ = payload.get("license")
    if license_ is not None:
        license_ = _reader_text(_one_line(license_, "license", source), "license", source)

    protocol = payload.get("protocol")
    reason = payload.get("protocol_reason")
    if protocol is not None and protocol != PROTOCOL_WITHHELD:
        raise DepositDeclarationError(
            f"{source}: 'protocol' must be {PROTOCOL_WITHHELD!r} or absent, not {protocol!r}"
        )
    if protocol is None:
        if reason is not None:
            raise DepositDeclarationError(
                f"{source}: 'protocol_reason' is given but 'protocol' is not "
                f"{PROTOCOL_WITHHELD!r}; drop the reason, or withhold the protocol"
            )
    else:
        if reason is None:
            raise DepositDeclarationError(
                f"{source}: 'protocol' is {PROTOCOL_WITHHELD!r}, so 'protocol_reason' (one "
                "line saying why) is required"
            )
        # The reason is printed in the manifest that ships with the paper, which passes the
        # paper vocabulary check whole (D4).
        reason = _reader_text(_one_line(reason, "protocol_reason", source),
                              "protocol_reason", source)

    files = payload.get("files", [])
    if not isinstance(files, list):
        raise DepositDeclarationError(f"{source}: 'files' must be a list of objects")
    entries = [_parse_entry(raw, i, source) for i, raw in enumerate(files)]

    seen: dict = {}
    for entry in entries:
        if entry.name is None:
            continue
        key = (entry.folder, entry.name.lower())
        if key in seen:
            raise DepositDeclarationError(
                f"{source}: files[{entry.index}]: 'name' {entry.name!r} is the name of "
                f"files[{seen[key].index}] ({seen[key].name!r}) in paper/deposit/"
                f"{entry.folder}/; names in one folder must differ in more than letter case"
            )
        seen[key] = entry

    return DepositDeclaration(
        spec_id=spec_id, license=license_, protocol_reason=reason, files=tuple(entries),
    )


def _protocol_record_files(run_dir: Path) -> List[Path]:
    """The run's protocol files as the record keeps them (D1): never a declared source."""
    run_dir = Path(run_dir)
    out = [run_dir / "spec.json"]
    out.extend(sorted((run_dir / "checkpoints").glob("amendment-v*.json")))
    return out


def _inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


#: The folders of a run directory whose files are the record itself; their files carry record
#: identifiers, which never reach what a reader receives (D4).
RECORD_DIRS: Tuple[str, ...] = ("evidence", "claims", "verdicts", "checkpoints")


def _record_part(resolved: Path, runs_dir: Path) -> Optional[str]:
    """The part of a run's record ``resolved`` lies in (``runs/<id>/evidence/``, or a
    top-level ``runs/<id>/<name>.json``), or ``None``. Every run under ``runs/`` counts."""
    try:
        parts = resolved.relative_to(runs_dir).parts
    except ValueError:
        return None
    if len(parts) >= 3 and parts[1] in RECORD_DIRS:
        return f"runs/{parts[0]}/{parts[1]}/"
    if len(parts) == 2 and parts[1].lower().endswith(".json"):
        return f"runs/{parts[0]}/{parts[1]}"
    return None


def entry_source_path(
    entry: DepositEntry, run_dir: Path, *, source: str = DEPOSIT_FILE
) -> Path:
    """The file ``entry.source`` names, looked up in ``run_dir`` first, then the workspace
    (``run_dir``'s grandparent), as a ``code_ref`` is (D3).

    Raises:
        DepositDeclarationError: (naming the entry index) no such file; the path with every
            symbolic link resolved lies outside the workspace; it is one of the run's
            protocol files (D1 ships those), lies under ``runs/<id>/paper/`` (the bundle), or
            is part of a run's record (``evidence/``, ``claims/``, ``verdicts/``,
            ``checkpoints/`` or a top-level ``*.json`` of any run under ``runs/``), whose files
            carry record identifiers (D4).
    """
    run_dir = Path(run_dir)
    workspace = run_dir.parent.parent
    where = f"{source}: files[{entry.index}]"
    found: Optional[Path] = None
    for root in (run_dir, workspace):
        candidate = root / entry.source
        # os.path.isfile answers False instead of raising for a name the OS rejects.
        if os.path.isfile(candidate):
            found = candidate
            break
    if found is None:
        raise DepositDeclarationError(
            f"{where}: 'source' {entry.source!r} is not a file in runs/{run_dir.name}/ or in "
            "the workspace"
        )
    try:
        resolved = found.resolve()
    except (OSError, RuntimeError) as e:
        raise DepositDeclarationError(
            f"{where}: 'source' {entry.source!r} cannot be resolved ({e})") from e
    if not _inside(resolved, workspace.resolve()):
        raise DepositDeclarationError(
            f"{where}: 'source' {entry.source!r} resolves to {resolved}, outside the "
            "workspace; copy the file into the workspace and declare the copy"
        )
    history = (run_dir / "spec_history").resolve()
    if _inside(resolved, history) or resolved in {
            p.resolve() for p in _protocol_record_files(run_dir)}:
        raise DepositDeclarationError(
            f"{where}: 'source' {entry.source!r} is a protocol file of the run; the protocol "
            "ships by default under paper/deposit/protocol/"
        )
    if _inside(resolved, (run_dir / "paper").resolve()):
        raise DepositDeclarationError(
            f"{where}: 'source' {entry.source!r} lies under runs/{run_dir.name}/paper/, the "
            "bundle render writes"
        )
    part = _record_part(resolved, run_dir.parent.resolve())
    if part is not None:
        raise DepositDeclarationError(
            f"{where}: 'source' {entry.source!r} lies in {part}, part of the record, whose "
            "files carry record identifiers; write the values the paper needs to a file "
            "outside the record and declare that file"
        )
    return found


def _resolved(declaration: DepositDeclaration, run_dir: Path, source: str
              ) -> DepositDeclaration:
    for entry in declaration.files:
        entry_source_path(entry, run_dir, source=source)
    return declaration


def read_deposit_declaration(
    data: bytes, run_dir: Path, spec_id: str, *, source: str
) -> DepositDeclaration:
    """Validate the bytes of a declaration file (``--deposit``) for ``run_dir``: JSON,
    :func:`parse_deposit_declaration` and every entry's source (:func:`entry_source_path`).

    Raises:
        DepositDeclarationError: as those do, the message naming ``source``.
    """
    try:
        payload = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as e:
        raise DepositDeclarationError(f"{source}: not readable JSON ({e})") from e
    return _resolved(parse_deposit_declaration(payload, spec_id, source=source), run_dir,
                     source)


def load_deposit_declaration(run_dir: Path, spec_id: str) -> Optional[DepositDeclaration]:
    """Read and validate ``run_dir/deposit.json``; ``None`` when the run has none.

    Raises:
        DepositDeclarationError: the file is not JSON, or fails
            :func:`read_deposit_declaration`.
    """
    path = Path(run_dir) / DEPOSIT_FILE
    if not path.is_file():
        return None
    source = f"runs/{Path(run_dir).name}/{DEPOSIT_FILE}"
    try:
        data = path.read_bytes()
    except OSError as e:
        raise DepositDeclarationError(f"{source}: not readable ({e})") from e
    return read_deposit_declaration(data, run_dir, spec_id, source=source)


@dataclass(frozen=True)
class DeclarationFile:
    """A declaration passed with ``--deposit``: its exact bytes and where they came from.

    Render validates it against the run, then copies the bytes to ``runs/<id>/deposit.json``
    (D2)."""

    data: bytes
    label: str

    @classmethod
    def read(cls, path: Path) -> "DeclarationFile":
        """Read ``path``; :class:`OSError` when it cannot be read."""
        return cls(data=Path(path).read_bytes(), label=str(path))


__all__ = [
    "DATA_FOLDER",
    "DEPOSIT_FILE",
    "INPUTS_FOLDER",
    "KIND_STUDY_DATA",
    "KIND_THIRD_PARTY_DATA",
    "NOT_REDISTRIBUTED",
    "ORIGINS",
    "ORIGIN_DERIVED",
    "ORIGIN_EXTERNAL",
    "ORIGIN_RECORDED",
    "PLAIN_NAME_RE",
    "PROTOCOL_WITHHELD",
    "REDISTRIBUTION_ASSERTED",
    "REDISTRIBUTION_TERMS",
    "RECORD_DIRS",
    "RESERVED_NAMES",
    "DeclarationFile",
    "DepositDeclaration",
    "DepositDeclarationError",
    "DepositEntry",
    "entry_source_path",
    "load_deposit_declaration",
    "parse_deposit_declaration",
    "read_deposit_declaration",
    "windows_name_problem",
]
