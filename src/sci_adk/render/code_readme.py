"""
The README of the deposited code: ``paper/code/README.md`` (design/paper-publishing-requirements.md
§3, "The code README").

The reproduction bundle ships each script the record names under ``paper/code/`` and a
``paper/reproduce.py`` that checks their hashes and runs nothing. This README tells the
paper's reader what the bundle does not: for each script, in the order its first result was
recorded, its SHA-256, the input files its recorded results name and whether the paper
distributes each (from the deposit manifest, with the cited source of one it does not), the
files those results wrote, the numbers printed in the paper that come from them (the run's
``numbers.json``), and the figures drawn from them (from the figure specs given to render).
Recorded-result ids appear only as cross-references into the record shipped with the paper
(``deposit/record.tex``), explained once at the top.

Render writes it; ``verify`` rebuilds it from the record with the same function and fails a
README that differs (figure lines aside: the figure specs are given to render, not recorded,
so :func:`strip_figure_lines` takes them out of both before the comparison).

Also here: :func:`local_path_warnings`, the render warning for a shipped text file that holds
an absolute local path.

PURE (text in, text out) and deterministic; English and ASCII only.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from sci_adk.core.deposit import KIND_STUDY_DATA, KIND_THIRD_PARTY_DATA
from sci_adk.core.evidence import EvidenceItem
from sci_adk.core.numbers import NumberList, NumberSource

CODE_README_NAME = "README.md"
# The first line of every README render writes: a re-render replaces (or removes) only a file
# that starts with it, and verify tells a README render did not write from a stale one.
CODE_README_MARKER = (
    "<!-- Written by sci-adk render from the run record; re-render instead of editing. -->"
)

_FIGURES_HEADER = "- Figures drawn from these results:"
_FIGURE_LINE = "  - Figure "

_INTRO = """\
# Code

This folder holds the scripts that produced the results reported in the paper, each byte for
byte as it was recorded. They are listed in the order their first result was recorded; a
result whose record names several scripts is listed under the first one it names. For each
script: its SHA-256; the input files its results name, whether each is distributed with the
paper, and which script wrote it when the record says; the files its results wrote; and the
numbers printed in the paper that come from its results. Each file is named by the fullest
path the record gives it.

Names such as `evi-...` identify recorded results in the analysis record distributed with
the paper (`deposit/record.tex` in the paper's folder), which lists each one with its time
and the code and data it names.

`../reproduce.py` checks that each script here has the SHA-256 recorded for it. It runs none
of them: the record does not hold the command lines or arguments the scripts were run with
(beyond what a result's description in the record states), and some input files cannot be
redistributed with the paper; each input below says whether it is distributed and, when it
is not, the source the paper cites for it. Paths are given as recorded, relative to the
folder the study was run in."""

_DOCUMENT_LABELS = {"draft.tex": "", "si.tex": ", supplementary information"}


@dataclass(frozen=True)
class ReadmeScript:
    """One shipped script: its ``paper/code/`` name, SHA-256, the ids of the recorded
    results whose code reference names it, in record order, and those of them whose code
    reference names another shipped script first (``also_named_ids``): a result is listed
    under the first script its code reference names."""

    filename: str
    sha256: str
    evidence_ids: Tuple[str, ...]
    also_named_ids: Tuple[str, ...] = ()


@dataclass(frozen=True)
class DepositedFile:
    """One declared data file of the deposit manifest: its path under ``paper/deposit/``
    (``""`` when it is not distributed), its SHA-256 and the bib keys it cites."""

    path: str
    sha256: str
    cite: Tuple[str, ...]


@dataclass(frozen=True)
class FigureLink:
    """A figure of the paper drawn from recorded results: its printed label (``Figure 2``,
    ``Figure S1``), its id and the ids of the results it plots."""

    label: str
    figure_id: str
    evidence_ids: Tuple[str, ...]


# -- reading file names and hashes out of recorded free text ---------------------------

_HASH_RE = re.compile(
    r"(?i)(?<![0-9a-z])sha-?256(?:\s*[=:]\s*|\s+)([0-9a-f]{64})(?![0-9a-f])"
)
_TOKEN_RE = re.compile(r"\S+")
_LEAD = "([{<\"'`"
_TRAIL = ";,:)]}>\"'`."
_EXTENSION_RE = re.compile(r"\.[A-Za-z][A-Za-z0-9]{0,9}$")
_DOI_RE = re.compile(r"(?i)^(?:doi:)?10\.\d{4,9}/")


def _clean_token(token: str) -> str:
    return token.lstrip(_LEAD).rstrip(_TRAIL)


def _file_like(token: str) -> bool:
    """Whether a cleaned token reads as a file path: a directory part or an extension that
    starts with a letter -- never a URL, a DOI or a hash keyword."""
    if not token or "://" in token or _DOI_RE.match(token):
        return False
    if token.lower().startswith("sha256") or token.lower().startswith("sha-256"):
        return False
    return "/" in token or "\\" in token or _EXTENSION_RE.search(token) is not None


@dataclass(frozen=True)
class _Mention:
    """A file recorded free text names: where (``start``/``end``), its name (``None`` when
    it is named only by its hash) and its SHA-256 (``None`` when none is written)."""

    start: int
    end: int
    name: Optional[str]
    sha: Optional[str]


def _mentions(text: Optional[str]) -> List[_Mention]:
    """The file mentions of recorded free text, in order (see :func:`files_named`)."""
    if not text:
        return []
    tokens = [(m.start(), m.end(), m.group(0)) for m in _TOKEN_RE.finditer(text)]
    used: set[int] = set()
    found: List[_Mention] = []
    for match in _HASH_RE.finditer(text):
        index = next(i for i, (s, e, _t) in enumerate(tokens) if s <= match.start() < e)
        used.update(i for i, (s, e, _t) in enumerate(tokens) if s < match.end() and e > match.start())
        name: Optional[str] = None
        start = match.start()
        if tokens[index][0] == match.start() and index > 0:
            candidate = _clean_token(tokens[index - 1][2])
            if _file_like(candidate):
                name = candidate
                start = tokens[index - 1][0]
                used.add(index - 1)
        found.append(_Mention(start, match.end(), name, match.group(1).lower()))
    for i, (start, end, token) in enumerate(tokens):
        cleaned = _clean_token(token)
        if i not in used and _file_like(cleaned):
            found.append(_Mention(start, end, cleaned, None))
    return sorted(found, key=lambda m: m.start)


def files_named(text: Optional[str]) -> List[Tuple[Optional[str], Optional[str]]]:
    """The files recorded free text names: ``(name or None, sha256 or None)`` in order. PURE.

    A hash written ``sha256=<64 hex>``, ``sha256 <64 hex>`` or ``SHA-256: <64 hex>`` belongs
    to the word right before it when that word reads as a file path; otherwise it is a file
    named only by its hash. A file path with no hash after it is a file without one. URLs,
    DOIs and words without a directory part or a letter-led extension are not files.
    """
    out: List[Tuple[Optional[str], Optional[str]]] = []
    for mention in _mentions(text):
        if (mention.name, mention.sha) not in out:
            out.append((mention.name, mention.sha))
    return out


# "(written by <script> [sha256=<hex>])" right after a file a data description names: the
# record saying which script wrote that file.
_WRITTEN_BY_RE = re.compile(
    r"(?i)\(?\s*written\s+by\s+([^\s(),;]+)"
    r"(?:\s+sha-?256(?:\s*[=:]\s*|\s+)([0-9a-f]{64})(?![0-9a-f]))?"
)


def _written_by(
    text: Optional[str],
) -> Tuple[List[Tuple[_Mention, str, Optional[str]]], List[Tuple[int, int]]]:
    """The "written by" statements of recorded free text: ``(file, script as written, its
    sha256 or None)`` for each statement that follows a file mention with nothing but
    spaces or a comma between, and the span of every statement (the script a statement
    names is code it names, not data the result read)."""
    if not text:
        return [], []
    mentions = _mentions(text)
    stated: List[Tuple[_Mention, str, Optional[str]]] = []
    spans: List[Tuple[int, int]] = []
    for match in _WRITTEN_BY_RE.finditer(text):
        spans.append((match.start(), match.end()))
        before = [m for m in mentions if m.end <= match.start()]
        if not before:
            continue
        last = max(before, key=lambda m: m.end)
        if text[last.end:match.start()].strip(" \t\r\n,"):
            continue
        sha = match.group(2).lower() if match.group(2) else None
        stated.append((last, _clean_token(match.group(1)), sha))
    return stated, spans


def _ascii(text: str) -> str:
    """``text`` folded to ASCII: accents dropped, any other character written ``?``."""
    out: List[str] = []
    for ch in unicodedata.normalize("NFKD", text):
        if ord(ch) < 0x80:
            out.append(ch)
        elif not unicodedata.combining(ch):
            out.append("?")
    return "".join(out).replace("\n", " ").replace("\r", " ")


# -- the README ------------------------------------------------------------------------

def _created(ev: EvidenceItem) -> datetime:
    at = ev.created_at
    return at.replace(tzinfo=timezone.utc) if at.tzinfo is None else at


def _source_text(cite: Sequence[str], dois: Mapping[str, str]) -> str:
    parts = []
    for key in cite:
        doi = dois.get(key)
        parts.append(f"references.bib entry {key}" + (f" (doi:{doi})" if doi else ""))
    return " and ".join(_ascii(p) for p in parts)


def _distribution(sha: str, deposited: Mapping[str, DepositedFile],
                  dois: Mapping[str, str]) -> str:
    entry = deposited.get(sha)
    if entry is not None and entry.path:
        return f"distributed with the paper as deposit/{_ascii(entry.path)}"
    text = "not distributed with the paper"
    if entry is not None and entry.cite:
        text += "; source: " + _source_text(entry.cite, dois)
    return text


def _file_label(name: Optional[str], sha: Optional[str]) -> str:
    if name is None:
        return f"a file the record names only by its SHA-256, {sha}"
    return f"`{_ascii(name)}`" + (f", SHA-256 {sha}" if sha else "")


# A file is (its name as the README prints it, or None; its SHA-256, or None).
_File = Tuple[Optional[str], Optional[str]]

_BOTH = "recorded as both an input and an output of these results"


def _same_file(a: _File, b: _File) -> bool:
    """Whether two mentions name the same file: the same SHA-256 when both carry one, else
    the same path."""
    if a[1] and b[1]:
        return a[1] == b[1]
    return a[0] is not None and a[0] == b[0]


def _depth(name: str) -> int:
    return name.count("/") + name.count("\\")


@dataclass(frozen=True)
class _Item:
    """One recorded result as the README reads it: the shipped scripts its code reference
    names (the first one first), the files its output reference names, the hashed files
    other than code its data description and code reference name, and whether its data
    description names code other than in a "written by" statement."""

    ev: EvidenceItem
    scripts: Tuple[str, ...]
    outputs: Tuple[_File, ...]
    data: Tuple[_File, ...]
    names_code: bool


# @MX:NOTE: [AUTO] the one rule for a file's README name and writer; render and verify both
#   build the README through render_code_readme, so a change here makes every rendered
#   README stale (verify asks for a re-render) rather than wrong on one side only.
class _Files:
    """The files the record names, each under one name, and the script that wrote each.

    A file is named by the fullest path the record gives it anywhere: the longest name
    recorded with its hash, or, for a name without a directory part (or a shorter one), the
    one recorded path that ends with it. Its writer (:meth:`writer`) is the script a data
    description says wrote it ("written by <script>"); otherwise the script named by every
    result whose output reference names it (the first such result's first script when no
    script is), results that also name it as data left out unless only such results name it.
    """

    def __init__(
        self,
        evidence: Sequence[EvidenceItem],
        scripts: Sequence[ReadmeScript],
        item_scripts: Mapping[str, Tuple[str, ...]],
    ) -> None:
        from sci_adk.loop.code_ref import code_ref_data_files, is_source_path  # lazy: cycle

        script_shas = {s.sha256 for s in scripts}
        by_sha = {s.sha256: s.filename for s in scripts}
        by_name = {s.filename: s.filename for s in scripts}
        raw = []
        self._fullest: Dict[str, str] = {}
        self._paths: set[str] = set()
        for ev in sorted(evidence, key=lambda e: (_created(e), e.id)):
            data = _mentions(ev.provenance.data_ref)
            art = _mentions(ev.result.artifact_ref if ev.result else None)
            code = [_Mention(-1, -1, path, sha.lower())
                    for path, sha in code_ref_data_files(ev.provenance.code_ref or "")]
            stated, spans = _written_by(ev.provenance.data_ref)
            raw.append((ev, data + code, art, stated, spans))
            for m in data + art + code:
                if m.name is None:
                    continue
                if _depth(m.name):
                    self._paths.add(m.name)
                if m.sha and (m.sha not in self._fullest
                              or _depth(m.name) > _depth(self._fullest[m.sha])):
                    self._fullest[m.sha] = m.name

        def is_code(m: _Mention) -> bool:
            return m.sha in script_shas or (m.name is not None and is_source_path(m.name))

        self.items: List[_Item] = []
        self._stated: List[Tuple[_File, str]] = []
        for ev, data, art, stated, spans in raw:
            hashed = [m for m in data if m.sha]
            self.items.append(_Item(
                ev, tuple(item_scripts.get(ev.id, ())),
                tuple(self.file(m) for m in art),
                tuple(self.file(m) for m in hashed if not is_code(m)),
                any(is_code(m) and not any(a <= m.start < b for a, b in spans) for m in hashed),
            ))
            for mention, script, sha in stated:
                base = re.split(r"[/\\]", script)[-1]
                writer = (by_sha.get(sha) if sha else None) or by_name.get(base) or base
                self._stated.append((self.file(mention), writer))

    def file(self, mention: _Mention) -> _File:
        name = (self._fullest.get(mention.sha) if mention.sha else None) or mention.name
        return (self._expand(name) if name else None, mention.sha)

    def _expand(self, name: str) -> str:
        hits = {p for p in self._paths if p != name and p.endswith("/" + name)}
        top = [p for p in hits if not any(q != p and q.endswith("/" + p) for q in hits)]
        return top[0] if len(top) == 1 else name

    def writer(self, f: _File) -> Tuple[Optional[str], str, Tuple[str, ...]]:
        """``(writer, basis, conflicting writers)``: basis ``"stated"`` (a "written by"
        statement), ``"output"`` (the results naming it as output), ``"both"`` (only results
        that also name it as data), ``"conflict"`` (statements naming different scripts,
        listed as the third element) or ``""`` (nothing names it as output)."""
        stated = tuple(dict.fromkeys(w for g, w in self._stated if _same_file(g, f)))
        if len(stated) == 1:
            return stated[0], "stated", ()
        if stated:
            return None, "conflict", stated
        namers = [it for it in self.items
                  if it.scripts and any(_same_file(o, f) for o in it.outputs)]
        writers = [it for it in namers if not any(_same_file(d, f) for d in it.data)]
        pool = writers or namers
        if not pool:
            return None, "", ()
        common = set(pool[0].scripts).intersection(*(it.scripts for it in pool[1:]))
        first = next((s for s in pool[0].scripts if s in common), pool[0].scripts[0])
        return first, ("output" if writers else "both"), ()


def _add(files: List[Tuple[_File, List[str]]], f: _File, notes: List[str]) -> None:
    """Add a file once; a mention with a hash replaces the same path mentioned without."""
    for i, (g, _n) in enumerate(files):
        if _same_file(g, f):
            if f[1] and not g[1]:
                files[i] = (f, notes)
            return
    files.append((f, notes))


def _writer_notes(files: _Files, f: _File, *, skip: Optional[str] = None) -> List[str]:
    """What the README says of a file's writer: ``written by <script>`` when the record
    identifies one (and it is not ``skip``), the conflicting scripts when it names several,
    nothing otherwise."""
    writer, basis, conflict = files.writer(f)
    if conflict:
        return ["the record names different scripts as having written it: "
                + ", ".join(_ascii(c) for c in conflict)]
    if writer and basis in ("stated", "output") and writer != skip:
        return [f"written by {_ascii(writer)}"]
    return []


def _classify(
    files: _Files, name: str, items: Sequence[_Item]
) -> Tuple[List[Tuple[_File, List[str]]], List[Tuple[_File, List[str]]], bool, bool]:
    """``(inputs, outputs, moved, own_written)`` of the results listed under script
    ``name``, each file with its notes.

    A file a result names as output is an output of these results when its writer is this
    script, no script, or another script the same code reference names (then noted); it is
    an INPUT when its writer is another script and the result also names it as data, or the
    code reference does not name that script. A file a result names as both, with no other
    writer on record, is noted as both. ``moved``: an output-named file became an input;
    ``own_written``: a data file left out because these results wrote it."""
    outputs: List[Tuple[_File, List[str]]] = []
    moved_in: Dict[str, List[_File]] = {}
    both: List[_File] = []
    for it in items:
        for f in it.outputs:
            writer, basis, _conflict = files.writer(f)
            read = any(_same_file(d, f) for d in it.data)
            if read and basis in ("both", "conflict"):
                both.append(f)
                _add(outputs, f, [_BOTH] + _writer_notes(files, f))
            elif read and writer == name:
                _add(outputs, f, [])
            elif read or (writer is not None and writer not in it.scripts):
                moved_in.setdefault(it.ev.id, []).append(f)
            else:
                _add(outputs, f, _writer_notes(files, f, skip=name))
    inputs: List[Tuple[_File, List[str]]] = []
    own_written = False
    for it in items:
        for f in it.data:
            if any(_same_file(f, b) for b in both):
                _add(inputs, f, [_BOTH] + _writer_notes(files, f))
            elif any(_same_file(f, o) for o, _notes in outputs):
                own_written = True
            else:
                _add(inputs, f, _writer_notes(files, f))
        for f in moved_in.get(it.ev.id, []):
            _add(inputs, f, _writer_notes(files, f))
    return inputs, outputs, bool(moved_in), own_written


def _input_line(f: _File, notes: List[str], deposited: Mapping[str, DepositedFile],
                dois: Mapping[str, str]) -> str:
    name, sha = f
    if sha:
        status = notes + [_distribution(sha, deposited, dois)]
        return f"  - {_file_label(name, sha)}: " + "; ".join(status)
    line = f"  - {_file_label(name, None)} (no SHA-256 recorded)"
    return line + (": " + "; ".join(notes) if notes else "")


def _output_line(f: _File, notes: List[str], deposited: Mapping[str, DepositedFile]) -> str:
    name, sha = f
    line = f"  - {_file_label(name, sha)}" + ("" if sha else " (no SHA-256 recorded)")
    line += "".join(f"; {note}" for note in notes)
    shipped = deposited.get(sha) if sha else None
    if shipped is not None and shipped.path:
        line += f"; distributed with the paper as deposit/{_ascii(shipped.path)}"
    return line


def _source_label(source: NumberSource, item_id: str) -> str:
    if source.kind == "evidence":
        return source.field if source.evidence == item_id else f"{source.field} of {source.evidence}"
    if source.kind == "spec":
        return f"the protocol's {source.spec}"
    return source.kind


def _numbers_by_item(
    numbers: Optional[NumberList], item_ids: Sequence[str]
) -> List[Tuple[str, str, List[str]]]:
    """``(item id, document, ["text (field)", ...])`` for every number the list sources
    from one of ``item_ids``, items in the given order, then the main text before the
    supplementary information, entries in list order."""
    if numbers is None:
        return []
    wanted = set(item_ids)
    groups: Dict[Tuple[str, str], List[str]] = {}
    for entry in numbers.numbers:
        if entry.role == "derived" and entry.operands:
            operands = list(entry.operands.values())
            for item_id in dict.fromkeys(
                op.evidence for op in operands if op.kind == "evidence" and op.evidence in wanted
            ):
                fields = ", ".join(_source_label(op, item_id) for op in operands)
                groups.setdefault((item_id, entry.document), []).append(
                    f"{_ascii(entry.text)} (derived from {_ascii(fields)})")
        elif (entry.role == "recorded" and entry.source is not None
              and entry.source.kind == "evidence" and entry.source.evidence in wanted):
            groups.setdefault((entry.source.evidence, entry.document), []).append(
                f"{_ascii(entry.text)} ({_ascii(entry.source.field)})")
    order = {item_id: i for i, item_id in enumerate(item_ids)}
    docs = list(_DOCUMENT_LABELS)
    keys = sorted(groups, key=lambda k: (order[k[0]], docs.index(k[1]) if k[1] in docs else 9))
    # A number the paper prints twice from the same field is listed once.
    return [(item_id, doc, list(dict.fromkeys(groups[(item_id, doc)])))
            for item_id, doc in keys]


def render_code_readme(
    scripts: Sequence[ReadmeScript],
    evidence: Sequence[EvidenceItem],
    *,
    deposited: Iterable[DepositedFile] = (),
    numbers: Optional[NumberList] = None,
    dois: Optional[Mapping[str, str]] = None,
    figures: Sequence[FigureLink] = (),
) -> str:
    """The text of ``paper/code/README.md`` for these shipped scripts. PURE, ASCII.

    ``scripts``: the shipped scripts with the results naming each; ``evidence``: the record
    (each result's time, data description, code reference and output files are read from
    it); ``deposited``: the data rows of the deposit manifest; ``numbers``: the run's number
    list; ``dois``: bib key -> DOI of the paper's ``references.bib``; ``figures``: the
    paper's figures drawn from recorded results. A result is listed (inputs, outputs,
    numbers, figures) under the first script its code reference names
    (``ReadmeScript.also_named_ids`` marks the others, which point to it); each file's name
    and writer come from the whole record (:class:`_Files`). Scripts are ordered by the
    earliest result listed under them (else the earliest naming them; ties in the given
    order), results inside a script by time.
    """
    dois = dois or {}
    deposited_by_sha = {d.sha256: d for d in deposited}

    # Each result is listed under the first shipped script its code reference names.
    primary: Dict[str, str] = {}
    for first_only in (True, False):
        for script in scripts:
            for i in script.evidence_ids:
                if not first_only or i not in script.also_named_ids:
                    primary.setdefault(i, script.filename)
    named: Dict[str, List[str]] = {}
    for script in scripts:
        for i in dict.fromkeys(script.evidence_ids):
            named.setdefault(i, []).append(script.filename)
    files = _Files(evidence, scripts, {
        i: (primary[i],) + tuple(s for s in names if s != primary[i])
        for i, names in named.items()
    })
    item_of = {it.ev.id: it for it in files.items}

    def listed(script: ReadmeScript, own: bool) -> List[_Item]:
        items = [item_of[i] for i in dict.fromkeys(script.evidence_ids)
                 if i in item_of and (primary[i] == script.filename) == own]
        return sorted(items, key=lambda it: (_created(it.ev), it.ev.id))

    blocks = [(script, listed(script, True), listed(script, False)) for script in scripts]
    order = sorted(
        range(len(blocks)),
        key=lambda i: (_created((blocks[i][1] or blocks[i][2])[0].ev)
                       if blocks[i][1] or blocks[i][2]
                       else datetime.max.replace(tzinfo=timezone.utc), i),
    )

    lines = [CODE_README_MARKER, "", _INTRO]
    for number, index in enumerate(order, start=1):
        script, items, also = blocks[index]
        ids = [it.ev.id for it in items]
        lines += ["", f"## {number}. {_ascii(script.filename)}", ""]
        lines.append(f"- SHA-256: {script.sha256}")
        lines.append("- Recorded results: " + (", ".join(_ascii(i) for i in ids)
                                               or "none listed under this script"))
        if also:
            lines.append(
                "- Also named by recorded results listed under the script their code "
                "reference names first: " + ", ".join(
                    f"{_ascii(it.ev.id)} ({_ascii(primary[it.ev.id])})" for it in also)
            )
        if not items:
            continue

        inputs, outputs, moved, own_written = _classify(files, script.filename, items)
        if inputs:
            lines.append("- Input files these results name:")
            lines += [_input_line(f, notes, deposited_by_sha, dois) for f, notes in inputs]
        elif own_written:
            lines.append("- Input files these results name: none besides files these results "
                         "wrote (listed below)")
        elif any(it.names_code for it in items):
            lines.append("- Input files these results name: none besides scripts")
        else:
            lines.append("- Input files these results name: none recorded")

        if outputs:
            lines.append("- Files these results wrote:")
            lines += [_output_line(f, notes, deposited_by_sha) for f, notes in outputs]
        elif moved:
            lines.append("- Files these results wrote: none recorded; the files their results "
                         "name as output were written by other scripts and are listed above "
                         "as inputs")
        else:
            lines.append("- Files these results wrote: none recorded")

        grouped = _numbers_by_item(numbers, ids)
        if grouped:
            lines.append("- Numbers in the paper from these results:")
            for item_id, doc, texts in grouped:
                where = _DOCUMENT_LABELS.get(doc, f", {doc}")
                lines.append(f"  - {_ascii(item_id)}{where}: " + ", ".join(texts))
        else:
            lines.append("- Numbers in the paper from these results: none")

        drawn = [(f, [i for i in f.evidence_ids if i in ids]) for f in figures]
        drawn = [(f, used) for f, used in drawn if used]
        if drawn:
            lines.append(_FIGURES_HEADER)
            for fig, used in drawn:
                # "  - Figure 2 (...)": the form strip_figure_lines recognises.
                lines.append(
                    f"  - {_ascii(fig.label)} ({_ascii(fig.figure_id)}): "
                    + ", ".join(_ascii(i) for i in used)
                )
    return "\n".join(lines) + "\n"


def strip_figure_lines(text: str) -> str:
    """``text`` without its figure lines (each "Figures drawn from these results" line and
    the figure items under it): the figure specs are given to render and not recorded, so
    verify compares a README without them. PURE."""
    out: List[str] = []
    in_figures = False
    for line in text.split("\n"):
        if line == _FIGURES_HEADER:
            in_figures = True
            continue
        if in_figures and line.startswith(_FIGURE_LINE):
            continue
        in_figures = False
        out.append(line)
    return "\n".join(out)


def written_by_render(text: str) -> bool:
    """Whether a ``paper/code/README.md`` was written by render (its first line). PURE."""
    return text.split("\n", 1)[0].rstrip("\r") == CODE_README_MARKER


def deposited_files(records: Optional[Sequence[Mapping[str, str]]]) -> List[DepositedFile]:
    """The declared data rows of a parsed deposit manifest (study and third-party data;
    the protocol, record and bibliography rows are left out). PURE."""
    out: List[DepositedFile] = []
    for row in records or []:
        if row.get("kind") not in (KIND_STUDY_DATA, KIND_THIRD_PARTY_DATA):
            continue
        cite = tuple(c for c in (row.get("cite") or "").split(";") if c)
        out.append(DepositedFile(row.get("file") or "", (row.get("sha256") or "").lower(), cite))
    return out


def bib_dois(bib: Optional[str]) -> Dict[str, str]:
    """``{key: DOI}`` of a ``references.bib`` text (entries without a DOI left out). PURE."""
    if not bib:
        return {}
    from sci_adk.search.literature_merge import parse_bib_entries  # lazy: cycle

    return {e.key: e.doi for e in parse_bib_entries(bib) if e.doi}


# -- absolute local paths in shipped text files -----------------------------------------

_LOCAL_PATH_RE = re.compile(
    r"(?<![\w./~\-])(?:"
    r"/home/[^/\s'\"]+/"
    r"|/Users/[^/\s'\"]+/"
    r"|/root/"
    r"|/mnt/[A-Za-z]/Users/[^/\s'\"]+"
    r"|[A-Za-z]:[\\/]{1,2}Users[\\/]{1,2}[^\\/\s'\"]+"
    r"|\\\\wsl(?:\.localhost|\$)\\"
    r")"
)


def local_path_warnings(files: Mapping[str, bytes], home: Optional[str] = None) -> List[str]:
    """One render warning per shipped text file holding an absolute local path. PURE.

    ``files`` maps the shipped file's name (``paper/code/...``, ``paper/deposit/data/...``) to
    its bytes. A path under a home directory (``/home/<name>/``, ``/Users/<name>/``,
    ``C:\\Users\\<name>``, ``/mnt/c/Users/<name>``, ``/root/``), a WSL share, or under
    ``home`` (the author's home directory, when given) counts; the warning names the file and
    the number of lines holding one. A file with a NUL byte is binary and not read.
    """
    patterns = [_LOCAL_PATH_RE]
    if home and home.rstrip("/\\") not in ("", "/"):
        patterns.append(re.compile(r"(?<![\w./~\-])" + re.escape(home.rstrip("/\\")) + r"(?=[/\\])"))
    lines: List[str] = []
    for name in sorted(files):
        data = files[name]
        if b"\x00" in data[:8192]:
            continue
        text = data.decode("utf-8", errors="replace")
        hits = [line for line in text.splitlines() if any(p.search(line) for p in patterns)]
        if hits:
            noun = "line" if len(hits) == 1 else "lines"
            lines.append(
                f"{name} has {len(hits)} {noun} holding an absolute local path -- a reader's "
                "copy cannot open it, and it names the author's machine; write such paths "
                "relative to the folder the study runs in"
            )
    return lines


__all__ = [
    "CODE_README_MARKER",
    "CODE_README_NAME",
    "DepositedFile",
    "FigureLink",
    "ReadmeScript",
    "bib_dois",
    "deposited_files",
    "files_named",
    "local_path_warnings",
    "render_code_readme",
    "strip_figure_lines",
    "written_by_render",
]
