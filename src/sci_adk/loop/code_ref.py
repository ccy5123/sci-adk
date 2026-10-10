"""
How a recorded ``provenance.code_ref`` resolves to generating code (F3 reproduction bundle).

A ``code_ref`` is text written by whoever recorded the Evidence. The reproduction bundle
(design/paper-publishing-requirements.md §3) ships the code a ``code_ref`` names, so the
compiler (which copies scripts into ``paper/code/`` and lists them, with their hashes, in
``paper/reproduce.py``) and ``verify`` (which gates that bundle) must read a ``code_ref``
the SAME way. This module is that one reading:

  1. The WHOLE ``code_ref``, taken as a path, names an existing file -> that file is the
     script. (The original rule; it keeps a path that contains spaces working.)
  2. Otherwise the LEADING whitespace-delimited token (one trailing ``;`` or ``,`` dropped)
     is the path, optionally followed by ``sha256=<64 hex>``. Everything after that is free
     text and is ignored -- a second script named in it is NOT followed.
       - the token names no existing file -> a POINTER (a bare commit hash, a decision ref
         such as ``prior_work:searched``, an unresolvable name), exactly as before;
       - it names a file and no hash follows -> the script;
       - a hash follows and the file's sha256 matches it -> the script;
       - a hash follows and does NOT match -> a POINTER, with the mismatch reported: the
         file on disk is not the code the record names, so it is never shipped as if it
         were.

A relative path is looked up under the run dir first, then the workspace; an absolute path
is taken as-is. Read-only and deterministic: it stats and hashes files, never writes, runs
nothing, and calls no LLM.

A ``code_ref`` often names more than one script, e.g. (a real run)::

    analysis/X/s4_h1_fit.py sha256=<hex> (input built by analysis/X/s1_select_records.py
    sha256=<hex> and s3_build_chemicals.py sha256=<hex>); no git commit (...)

:func:`resolve_code_ref_scripts` reads EVERY script a ``code_ref`` names: the leading path
(as above) plus each later word directly followed by ``sha256=<64 hex>``. A later word with
no hash is free text and is not followed (the recorded hash is what makes it a script
reference). A later path that is not found under the run dir or the workspace is also tried
beside the first script that resolved -- accepted only when its sha256 matches the recorded
one, since that location is a guess (``s3_build_chemicals.py`` above). The reproduction
bundle (compiler) and its gate (verify) both use this reading; :func:`resolve_code_ref`
remains the reading of the leading script alone.

Only SOURCE files are scripts. A ``code_ref`` may also name, with their hashes, the data its
script read::

    analysis/a.py sha256=<hex> (reads analysis/data.csv sha256=<hex> and
    analysis/table.xls sha256=<hex>)

A named path is a script only when :func:`is_source_path` accepts it: its extension is in
:data:`SOURCE_EXTENSIONS` (compared case-insensitively) or its file name is in
:data:`SOURCE_FILE_NAMES` -- or when it has no extension and the file it names starts with
a shebang (``#!``), which is how an extensionless script (``bin/run_all``) is written. That
one case reads the file's first two bytes; the compiler and ``verify`` both decide it here.
Any other path written with ``sha256=<64 hex>`` is a DATA REFERENCE
(:func:`code_ref_data_files`): the bundle lists it with its recorded hash and never copies
it (data can be large, licensed, or private, and the record does not say which script read
which file). ``verify`` hashes a data reference the workspace holds
(:func:`resolve_code_ref_data_files`): a file that no longer matches its recorded hash is
not the data the result was computed from. A non-source path written WITHOUT a hash is free
text, as before.
"""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

from sci_adk.core.evidence import EvidenceKind

# ``sha256=`` + exactly 64 hex digits, not followed by another hex digit (so a longer run
# is not mistaken for a hash). Matched only at the START of the text after the path token.
_SHA256_AFTER_PATH = re.compile(r"sha256=([0-9a-fA-F]{64})(?![0-9a-fA-F])")

# A word directly followed by ``sha256=<64 hex>``, anywhere in a code_ref: a script the
# code_ref names together with the hash recorded for it.
_PATH_THEN_SHA256 = re.compile(r"(\S+)\s+sha256=([0-9a-fA-F]{64})(?![0-9a-fA-F])")
# Punctuation that free text wraps a path in: "(input built by x.py sha256=...)".
_TOKEN_LEAD = "([{<\"'"
_TOKEN_TRAIL = ";,:)]}>\"'"

# Process/decision meta-records carry a decision pointer in ``code_ref`` (e.g.
# ``prior_work:searched``), not generating code, and hold ``bears_on=[]``. Reproduction is
# about the GENERATING code, so neither the bundle (compiler) nor its gate (verify) treats
# them as code to ship or require.
NON_REPRODUCIBLE_KINDS = frozenset(
    {
        EvidenceKind.PRIOR_WORK_DECISION,
        EvidenceKind.NOVELTY_DECISION,
        EvidenceKind.CONTESTED_RECORD,
        EvidenceKind.INQUIRY_DECISION,
    }
)

# @MX:NOTE: [AUTO] the fixed set of source-file extensions (lower-case, compared
#   case-insensitively): a path a code_ref names is shipped into paper/code/ only when it is
#   source. Everything else written with a hash is a data reference (listed, never copied).
#   Extend deliberately -- a data format added here would be copied into every paper.
SOURCE_EXTENSIONS = frozenset(
    {
        # Python (incl. Cython), R, Julia, MATLAB/Octave, notebooks
        ".py", ".pyx", ".pxd", ".ipynb", ".r", ".rmd", ".qmd", ".jl", ".m",
        # statistics packages and probabilistic-model languages
        ".do", ".ado", ".sas", ".sps", ".stan", ".jags", ".bug",
        # shells and scripting languages
        ".sh", ".bash", ".zsh", ".ps1", ".bat", ".cmd", ".pl", ".pm", ".rb", ".lua",
        ".tcl", ".awk", ".sed", ".php", ".groovy",
        # JavaScript / TypeScript
        ".js", ".mjs", ".cjs", ".jsx", ".ts", ".mts", ".cts", ".tsx",
        # compiled languages (incl. CUDA)
        ".c", ".h", ".cc", ".cpp", ".cxx", ".hpp", ".hh", ".cu", ".cuh", ".f", ".for",
        ".f77", ".f90", ".f95", ".f03", ".f08", ".rs", ".go", ".java", ".scala", ".kt",
        ".kts", ".cs", ".vb", ".swift", ".dart", ".zig", ".nim",
        # functional languages
        ".hs", ".ml", ".mli", ".fs", ".fsx", ".ex", ".exs", ".erl", ".clj", ".cljs",
        # mathematics, optimisation and proof systems
        ".sage", ".wl", ".wls", ".nb", ".mpl", ".gms", ".lean", ".thy",
        # query and workflow languages
        ".sql", ".mk", ".smk", ".nf", ".wdl", ".cwl",
    }
)

# Extensionless build/workflow files that are source by name.
SOURCE_FILE_NAMES = frozenset({"Makefile", "makefile", "GNUmakefile", "Snakefile", "Dockerfile"})


@dataclass(frozen=True)
class CodeRefResolution:
    """What one ``code_ref`` resolves to.

    Attributes:
        script: the file to ship and drive as the recorded generating code, or ``None``
            (the ``code_ref`` is a POINTER).
        named_path: the path token as recorded, when it names an existing file.
        expected_sha256: the hash the ``code_ref`` records for that file, if any.
        actual_sha256: the sha256 of that file on disk now (set when a hash was recorded).
    """

    script: Optional[Path] = None
    named_path: Optional[str] = None
    expected_sha256: Optional[str] = None
    actual_sha256: Optional[str] = None

    @property
    def hash_mismatch(self) -> bool:
        """True when the named file exists but does not hash to the recorded sha256."""
        return (
            self.expected_sha256 is not None
            and self.actual_sha256 is not None
            and self.expected_sha256 != self.actual_sha256
        )


def parse_code_ref(code_ref: str) -> tuple[str, Optional[str]]:
    """Split ``code_ref`` into ``(leading path token, sha256 or None)``. PURE.

    The token is the first whitespace-delimited word with one trailing ``;`` or ``,``
    removed. The hash is taken only when ``sha256=<64 hex>`` is the very next word (also
    when the token ended in ``;``); it is returned lower-cased. Anything else -- a hash of a
    different length, a hash further along the text -- is free text, so ``(token, None)``.
    """
    parts = code_ref.strip().split(None, 1)
    if not parts:
        return "", None
    token = parts[0]
    if token[-1] in ";,":
        token = token[:-1]
    rest = parts[1] if len(parts) > 1 else ""
    match = _SHA256_AFTER_PATH.match(rest)
    return token, (match.group(1).lower() if match else None)


# @MX:NOTE: [AUTO] the reading of a code_ref's LEADING script only (demoted from ANCHOR: the
#   compiler and verify now read every named script via resolve_code_ref_scripts, which
#   applies this same rule to the leading path and, unlike this function, ships only
#   source files).
def resolve_code_ref(code_ref: str, run_dir: Path, workspace_dir: Path) -> CodeRefResolution:
    """Resolve ``code_ref`` to the recorded script, or to a POINTER (see the module docs).

    Never raises for an odd ``code_ref``: free text that cannot be a path (a NUL byte, a
    name longer than the filesystem allows) is simply not a file, and an unreadable file
    cannot be hashed, so both are POINTERS.
    """
    ref = code_ref.strip()
    if not ref:
        return CodeRefResolution()
    whole = _existing_file(ref, run_dir, workspace_dir)
    if whole is not None:
        return CodeRefResolution(script=whole)

    token, expected = parse_code_ref(ref)
    named = _existing_file(token, run_dir, workspace_dir) if token else None
    return _resolve_named(token, named, expected)


@dataclass(frozen=True)
class NamedScript:
    """One script a ``code_ref`` names.

    Attributes:
        path: the path as written in the ``code_ref``.
        recorded_sha256: the hash written right after it, if any (lower-cased).
        resolution: what that path resolves to (``resolution.script`` is ``None`` when the
            file is missing, unreadable, or does not hash to ``recorded_sha256``).
    """

    path: str
    recorded_sha256: Optional[str]
    resolution: CodeRefResolution


def parse_code_ref_scripts(code_ref: str) -> List[Tuple[str, Optional[str]]]:
    """Every ``(path, sha256 or None)`` a ``code_ref`` names, in order. PURE.

    The first pair is :func:`parse_code_ref`'s (the leading path and its hash, if the hash
    directly follows it). Then every later word directly followed by ``sha256=<64 hex>``.
    Every path has the punctuation free text wraps it in (``(`` before, ``;`` ``,`` ``)``
    after) removed, and an exact repeat of a pair already listed is dropped. Empty text ->
    ``[]``.
    """
    lead, lead_hash = parse_code_ref(code_ref)
    lead = lead.lstrip(_TOKEN_LEAD).rstrip(_TOKEN_TRAIL) or lead
    if not lead:
        return []
    pairs: List[Tuple[str, Optional[str]]] = [(lead, lead_hash)]
    for match in _PATH_THEN_SHA256.finditer(code_ref.strip()):
        token = match.group(1).lstrip(_TOKEN_LEAD).rstrip(_TOKEN_TRAIL)
        pair = (token, match.group(2).lower())
        if token and pair not in pairs:
            pairs.append(pair)
    return pairs


# @MX:ANCHOR: [AUTO] the reading of EVERY script a code_ref names: the compiler ships each
#   resolved one into paper/code/ and lists it in reproduce.py, and verify's F3 gate checks
#   the same set (workspace hash + shipped copy + reproduce.py's script list).
# @MX:REASON: [AUTO] fan_in 3 (compiler._resolve_repro_listings, verify
#   _reproduction_bundle_problems, verify _reproduction_advisory). A second reading would let
#   the gate judge a bundle the render never produced.
def resolve_code_ref_scripts(
    code_ref: str, run_dir: Path, workspace_dir: Path
) -> List[NamedScript]:
    """Resolve every SOURCE script ``code_ref`` names (see the module docs), in order.

    The WHOLE ``code_ref`` naming an existing source file is one script, as in
    :func:`resolve_code_ref`. Otherwise each pair from :func:`parse_code_ref_scripts` whose
    path is source (:func:`is_source_path`) is looked up under the run dir, then the
    workspace; a later pair not found there is tried beside the first script that resolved,
    and that guessed file counts only when its sha256 matches the recorded one (a guessed
    file with another hash is not reported as a changed file -- it may simply be a different
    file). An extensionless path is a script when the file it names starts with a shebang
    (``#!``). Any other path that is not source is never a script: with a hash it is a data
    reference (:func:`code_ref_data_files`), without one it is free text or a pointer. Never
    raises for odd text.
    """
    ref = code_ref.strip()
    if not ref:
        return []
    whole = _existing_file(ref, run_dir, workspace_dir)
    if whole is not None and (is_source_path(ref) or _shebang_script(ref, whole)):
        return [NamedScript(path=ref, recorded_sha256=None,
                            resolution=CodeRefResolution(script=whole))]

    out: List[NamedScript] = []
    beside: Optional[Path] = None
    for index, (token, expected) in enumerate(parse_code_ref_scripts(ref)):
        source = is_source_path(token)
        if not source and not _extensionless(token):
            continue
        named = _existing_file(token, run_dir, workspace_dir)
        guessed = False
        if named is None and index > 0 and beside is not None and not Path(token).is_absolute():
            candidate = beside / token
            if os.path.isfile(candidate):
                named, guessed = candidate, True
        if not source and not _shebang_script(token, named):
            continue  # an extensionless path that is not a shebang script: data or text
        resolution = _resolve_named(token, named, expected)
        if guessed and resolution.script is None:
            resolution = CodeRefResolution()
        if beside is None and resolution.script is not None:
            beside = resolution.script.parent
        out.append(NamedScript(path=token, recorded_sha256=expected, resolution=resolution))
    return out


def is_source_path(path: str) -> bool:
    """Whether a path a ``code_ref`` names is a source file the bundle ships. PURE.

    True when the path's extension, lower-cased, is in :data:`SOURCE_EXTENSIONS`, or its
    file name is in :data:`SOURCE_FILE_NAMES`. Decided from the text alone (no filesystem),
    so the compiler and ``verify`` agree whatever the file holds. (An extensionless shebang
    script is the one case decided from the file: :func:`resolve_code_ref_scripts` reads it.)
    """
    name = re.split(r"[/\\]", path.strip())[-1]
    if name in SOURCE_FILE_NAMES:
        return True
    stem, dot, suffix = name.rpartition(".")
    return bool(stem and dot) and f".{suffix.lower()}" in SOURCE_EXTENSIONS


def code_ref_data_files(
    code_ref: str,
    run_dir: Optional[Path] = None,
    workspace_dir: Optional[Path] = None,
) -> List[Tuple[str, str]]:
    """The DATA references a ``code_ref`` names: ``(path, sha256)`` pairs, in order.

    Every path :func:`parse_code_ref_scripts` reads WITH a recorded hash that is not source
    (:func:`is_source_path`) and looks like a file path (it has a directory part or an
    extension -- a bare word such as ``outputs sha256=...`` is free text). The bundle lists
    these with their hash and never copies them.

    PURE when called with the text alone. Given the run and workspace dirs, an
    extensionless path that :func:`resolve_code_ref_scripts` reads as a shebang script is
    left out (it is shipped, not listed as data) -- the compiler passes both dirs, so a file
    is never both.
    """
    scripts: set[str] = set()
    if run_dir is not None and workspace_dir is not None:
        scripts = {
            ns.path for ns in resolve_code_ref_scripts(code_ref, run_dir, workspace_dir)
        }
    out: List[Tuple[str, str]] = []
    for path, digest in parse_code_ref_scripts(code_ref):
        if digest is None or is_source_path(path) or not _looks_like_file_path(path):
            continue
        if path not in scripts and (path, digest) not in out:
            out.append((path, digest))
    return out


@dataclass(frozen=True)
class NamedData:
    """One data file a ``code_ref`` names with its hash, as the workspace holds it now.

    Attributes:
        path: the path as written in the ``code_ref``.
        recorded_sha256: the hash written right after it (lower-cased).
        file: where the workspace holds that file, or ``None`` (not found).
        actual_sha256: the sha256 of ``file`` now (``None`` when not found or unreadable).
    """

    path: str
    recorded_sha256: str
    file: Optional[Path] = None
    actual_sha256: Optional[str] = None

    @property
    def missing(self) -> bool:
        """True when neither the run dir nor the workspace holds the file."""
        return self.file is None

    @property
    def hash_mismatch(self) -> bool:
        """True when the file is held but does not hash to the recorded sha256."""
        return self.actual_sha256 is not None and self.actual_sha256 != self.recorded_sha256


# @MX:NOTE: [AUTO] verify's reproduction gate FAILs on a data file whose hash changed and
#   advises on one the workspace does not hold; the compiler warns on the same mismatch.
#   Read-only: stats and hashes files, never copies or runs them.
def resolve_code_ref_data_files(
    code_ref: str, run_dir: Path, workspace_dir: Path
) -> List[NamedData]:
    """Every data reference ``code_ref`` names (:func:`code_ref_data_files`), looked up and
    hashed.

    A relative path is looked up under the run dir, then the workspace; one not found there
    is tried beside the first script the ``code_ref`` names that resolves, and that guessed
    file counts only when its sha256 matches the recorded one (as for a guessed script).
    Never raises for odd text.
    """
    beside = next(
        (ns.resolution.script.parent
         for ns in resolve_code_ref_scripts(code_ref, run_dir, workspace_dir)
         if ns.resolution.script is not None),
        None,
    )
    out: List[NamedData] = []
    for path, recorded in code_ref_data_files(code_ref, run_dir, workspace_dir):
        found = _existing_file(path, run_dir, workspace_dir)
        if found is not None:
            out.append(NamedData(path, recorded, found, _sha256_of(found)))
            continue
        if beside is not None and not Path(path).is_absolute():
            candidate = beside / path
            if os.path.isfile(candidate) and _sha256_of(candidate) == recorded:
                out.append(NamedData(path, recorded, candidate, recorded))
                continue
        out.append(NamedData(path, recorded))
    return out


def describe_data_mismatch(evidence_id: str, data: NamedData) -> str:
    """One line naming a changed data file: the Evidence id, the file, and both hashes."""
    return (
        f"{evidence_id}: code_ref names data file {data.path} with "
        f"sha256={data.recorded_sha256}, but that file now hashes to {data.actual_sha256}"
    )


def _looks_like_file_path(path: str) -> bool:
    name = re.split(r"[/\\]", path)[-1]
    return "/" in path or "\\" in path or bool(Path(name).suffix)


def _extensionless(path: str) -> bool:
    """True when the file name a path ends in has no extension and is not a source name."""
    name = re.split(r"[/\\]", path.strip())[-1]
    return bool(name) and "." not in name and name not in SOURCE_FILE_NAMES


def _shebang_script(path: str, file: Optional[Path]) -> bool:
    """True when ``path`` is extensionless and ``file`` (what it names) starts with ``#!``."""
    if file is None or not _extensionless(path):
        return False
    try:
        with open(file, "rb") as handle:
            return handle.read(2) == b"#!"
    except OSError:
        return False


def _resolve_named(
    token: str, named: Optional[Path], expected: Optional[str]
) -> CodeRefResolution:
    """What a path token that found ``named`` (or nothing) resolves to, given its hash."""
    if named is None:
        return CodeRefResolution()
    if expected is None:
        return CodeRefResolution(script=named, named_path=token)
    actual = _sha256_of(named)
    if actual is None:
        return CodeRefResolution()
    return CodeRefResolution(
        script=named if actual == expected else None,
        named_path=token,
        expected_sha256=expected,
        actual_sha256=actual,
    )


def describe_mismatch(evidence_id: str, resolution: CodeRefResolution) -> str:
    """One line naming a hash mismatch: the Evidence id, the file, and both hashes."""
    return (
        f"{evidence_id}: code_ref names {resolution.named_path} with "
        f"sha256={resolution.expected_sha256}, but that file now hashes to "
        f"{resolution.actual_sha256}"
    )


def _existing_file(ref: str, run_dir: Path, workspace_dir: Path) -> Optional[Path]:
    candidate = Path(ref)
    roots = (
        [candidate]
        if candidate.is_absolute()
        else [Path(run_dir) / candidate, Path(workspace_dir) / candidate]
    )
    for path in roots:
        # os.path.isfile, not Path.is_file: it answers False instead of raising for a name
        # the OS rejects (ENAMETOOLONG, an embedded NUL), which free text can produce.
        if os.path.isfile(path):
            return path
    return None


def _sha256_of(path: Path) -> Optional[str]:
    # Read in 1 MiB chunks: data files named in a code_ref are hashed on every render
    # and verify, and may be large.
    digest = hashlib.sha256()
    try:
        with open(path, "rb") as handle:
            for chunk in iter(lambda: handle.read(1 << 20), b""):
                digest.update(chunk)
    except OSError:
        return None
    return digest.hexdigest()


__all__ = [
    "CodeRefResolution",
    "NON_REPRODUCIBLE_KINDS",
    "NamedData",
    "NamedScript",
    "SOURCE_EXTENSIONS",
    "SOURCE_FILE_NAMES",
    "code_ref_data_files",
    "describe_data_mismatch",
    "describe_mismatch",
    "is_source_path",
    "parse_code_ref",
    "parse_code_ref_scripts",
    "resolve_code_ref",
    "resolve_code_ref_data_files",
    "resolve_code_ref_scripts",
]
