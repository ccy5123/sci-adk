#!/usr/bin/env python3
"""Package integrity self-check (field-agnostic).

Confirms the manuscript package is internally consistent and submission-clean:
  1. \\ref <-> \\label integrity, figure presence, brace balance (main.tex, si.tex)
  2. every \\cite key resolves to an entry in references.bib (and flags uncited entries)
  3. no toolchain vocabulary leaks into the author-facing prose (names the science, not the
     tool)
  4. the deposited files (``06_provenance/deposit.csv``): every row's file exists with the
     SHA-256 and size the row gives, every file in the folders the package rebuilds
     (``06_provenance/protocol/<run>/``, ``02_data/<run>/``, ``05_inputs/<run>/``) is a row, and
     every package path ``main.tex`` / ``si.tex`` name exists in the package

Exit 0 iff all four pass. Run from the package root: ``python3 04_scripts/check_package.py``.

This is the reviewer-facing companion to the ``package_requirements_clean`` verify gate: the
gate is the authoritative, in-process deterministic check; this script lets a reviewer who has
only the shipped package (and a Python interpreter) re-run the same structural checks by hand.
The gate also compares ``deposit.csv`` with the rows the record under ``runs/`` calls for; this
script cannot, and says so.
"""
import csv
import hashlib
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.dirname(HERE)
WS = os.path.dirname(PKG)
MAN = os.path.join(PKG, "01_manuscript")

# Toolchain terms that must NOT appear in author-facing prose (the science is named instead).
# A verbatim copy of the lists the package gate itself applies (sci_adk.render.paper:
# _PAPER_TOOL_PHRASES, _PAPER_TOOL_WORD_RE, _PAPER_TOOL_PROPER_RE, _PAPER_ARTIFACT_RES), so a
# reviewer re-running this script gets the gate's answer; sci-adk's test suite fails when the
# copies differ. Only compounds that name the authoring machinery are listed: the bare phrase
# "decision rule" is standard statistics, and "Evidence", "Claim" and "verify" are ordinary
# English.
TOOL_PHRASES = (
    "sci-adk",
    "frozen spec",
    "engine-derived",
    "the engine",
    "verify audit",
    "append-only",
    "evidence record",
    "belief state",
    "anti-harking",
    "result.point",
    "result.finding",
    "claim status",
    "evidence item",
    "record digest",
    "spec digest",
    "record fidelity",
    "frozen contract",
    "frozen decision rule",
    "pre-registered decision rule",
    "research compiler",
    "verify gate",
)
# A paper states a "result", not a "verdict".
TOOL_WORD_RE = re.compile(r"\b(?:verdict|verdicts)\b", re.IGNORECASE)
# "Spec" as the tool's proper noun; "specification" and lowercase "spec" are fine.
TOOL_PROPER_RE = re.compile(r"\bSpec\b")
# Run-artifact ids (by shape) and internal artifact file/directory names (any case).
ARTIFACT_RES = (
    re.compile(r"\bevi-[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?"),
    re.compile(r"\bclaim-(?:hyp|novelty)-[A-Za-z0-9._-]*[A-Za-z0-9]"),
    re.compile(
        r"\b(?:spec|pubreqs|pkgreqs|declarations|review|deposit|numbers(?:\.draft)?)\.json\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bcheckpoints/(?:amendment-v\d+|prior(?:\\_|_)work|science)\.json\b",
        re.IGNORECASE,
    ),
    re.compile(r"\bnovelty(?:\\_|_)sentences\.json\b", re.IGNORECASE),
    re.compile(r"\bspec\.v\d+\.json\b", re.IGNORECASE),
    re.compile(r"\bspec(?:\\_|_)history\b", re.IGNORECASE),
    re.compile(r"\b(?:checkpoints|science)\.md\b", re.IGNORECASE),
)


def toolvocab_hits(text):
    """(term, offset of its first occurrence) for each toolchain term in ``text``, in the
    order the package gate reports them (sci_adk.render.paper.check_paper_tool_vocabulary)."""
    low = text.lower()
    hits = []
    seen = set()

    def add(term, offset):
        if term not in seen:
            seen.add(term)
            hits.append((term, offset))

    for phrase in TOOL_PHRASES:
        at = low.find(phrase)
        if at >= 0:
            add(phrase, at)
    for m in TOOL_WORD_RE.finditer(text):
        add(m.group(0).lower(), m.start())
    m = TOOL_PROPER_RE.search(text)
    if m:
        add("Spec", m.start())
    for pattern in ARTIFACT_RES:
        for m in pattern.finditer(text):
            add(m.group(0), m.start())
    return hits


def toolvocab_leaks(text):
    """The distinct toolchain terms in ``text`` -- the package gate's answer."""
    return [term for term, _ in toolvocab_hits(text)]


def check_tex(path, check_figs=True):
    """ref/label integrity + figure presence + brace balance for one .tex. Returns (text, ok)."""
    with open(path) as fh:
        t = fh.read()
    name = os.path.basename(path)
    ok = True
    labels = set(re.findall(r"\\label\{([^}]+)\}", t))
    refs = set(re.findall(r"\\ref\{([^}]+)\}", t))
    miss = refs - labels
    print(f"[{name}] refs without a label: {sorted(miss) if miss else 'NONE (ok)'}")
    if miss:
        ok = False
    if check_figs:
        for im in re.findall(r"\\includegraphics\[[^]]*\]\{([^}]+)\}", t):
            p = os.path.join(os.path.dirname(path), "figures", im)
            status = "OK" if os.path.exists(p) else "MISSING"
            print(f"[{name}] figure {im}: {status}")
            if status == "MISSING":
                ok = False
    bal = t.count("{") == t.count("}")
    print(f"[{name}] braces balanced: {bal} ({t.count('{')} open / {t.count('}')} close)")
    if not bal:
        ok = False
    return t, ok


def check_citations(main_text):
    """Every \\cite key resolves in references.bib (+ flag uncited entries). Returns ok."""
    with open(os.path.join(MAN, "references.bib")) as fh:
        bib = fh.read()
    cited = set()
    for grp in re.findall(r"\\cite[a-zA-Z]*\{([^}]+)\}", main_text):
        cited |= {k.strip() for k in grp.split(",")}
    defined = set(re.findall(r"@\w+\{\s*([^,\s]+)\s*,", bib))
    missing = cited - defined
    print(f"[cite] {len(cited)} cite keys, {len(defined)} bib entries")
    print(f"[cite] cited keys missing from references.bib: "
          f"{sorted(missing) if missing else 'NONE (all wired)'}")
    uncited = defined - cited
    print(f"[cite] bib entries never cited: {sorted(uncited) if uncited else 'NONE'}")
    return not missing


def check_toolvocab(path):
    """No toolchain vocabulary in author-facing prose. Returns ok."""
    with open(path) as fh:
        t = fh.read()
    name = os.path.basename(path)
    hits = [(t[:at].count("\n") + 1, term) for term, at in toolvocab_hits(t)]
    if hits:
        print(f"[{name}] TOOLCHAIN-VOCAB LEAK ({len(hits)}): " +
              ", ".join(f"L{ln}:{tok}" for ln, tok in hits[:20]))
        return False
    print(f"[{name}] tool-vocabulary: clean (names the science)")
    return True


# -- deposited files (06_provenance/deposit.csv) --------------------------------------------
# A copy of the package gate's deposit-file checks that need nothing but the package
# (sci_adk.render.pkgreqs_checks.package_deposit_problems and
# sci_adk.render.deposit.package_name_problems); sci-adk's test suite fails when the patterns
# below differ from the gate's or the names messages do.
DEPOSIT_CSV = "06_provenance/deposit.csv"
DEPOSIT_COLUMNS = ("run", "file", "sha256", "bytes", "kind", "sha256_also_in", "cite",
                   "license", "description", "evidence")
PROTOCOL_ROOT = "06_provenance/protocol"
OWNED_ROOTS = (PROTOCOL_ROOT, "02_data", "05_inputs")
# Each package folder and the per-run paper folder its files come from (paper/deposit/<f>/).
PER_RUN_FOLDER = {PROTOCOL_ROOT: "protocol", "02_data": "data", "05_inputs": "inputs"}
RECORD = "06_provenance/record.tex"
RUN_INDEX = "06_provenance/run_index.csv"
PLAIN_NAME_RE = re.compile(r"[A-Za-z0-9_-][A-Za-z0-9._-]*")
URL_MASK_RES = (
    re.compile(r"\\(?:url|nolinkurl)\s*\{[^{}]*\}"),
    re.compile(r"\\href\s*\{[^{}]*\}"),
)
DEPOSIT_PATH_RE = re.compile(r"(?<![\w/.])deposit/[A-Za-z0-9._/-]*")
BARE_PROTOCOL_RE = re.compile(
    r"(?<![\w/.\-])(?:protocol|amendment)-v\d+\.json(?!\w)", re.IGNORECASE)
PACKAGE_PATH_RE = re.compile(
    r"(?<![\w/.])(?:02_data|05_inputs|06_provenance)/[A-Za-z0-9._/-]*")
TRAILING = ".,;:)"
FILE_WITH_EXTENSION_RE = re.compile(r"[^./][^/]*\.[A-Za-z0-9]+")
_PROTOCOL_DESCRIPTION_RE = re.compile(r"protocol, version (\d+)")
_AMENDMENT_DESCRIPTION_RE = re.compile(r"amendment that produced version (\d+)")
_WITHHELD = "; withheld: "


def _pkg_path(rel):
    return os.path.join(PKG, *rel.split("/"))


def _read(rel):
    """A package file's text, or None when it is missing or a symbolic link."""
    path = _pkg_path(rel)
    if os.path.islink(path) or not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8", errors="replace") as fh:
        return fh.read()


def has_deposit_trace():
    """Whether the package was assembled with deposit files: record.tex has a Protocol history
    section or run_index.csv a protocol_digest_sha256 column."""
    record = _read(RECORD)
    if record is not None and "\\section{Protocol history}" in record:
        return True
    index = _read(RUN_INDEX)
    return index is not None and "protocol_digest_sha256" in next(
        csv.reader(io.StringIO(index)), [])


def read_deposit_rows():
    """The rows of 06_provenance/deposit.csv as dicts, or None when it is missing or a link.
    Raises ValueError when its columns are not the package's."""
    text = _read(DEPOSIT_CSV)
    if text is None:
        return None
    try:
        reader = csv.reader(io.StringIO(text))
        header = next(reader, None)
        if header is None or tuple(header) != DEPOSIT_COLUMNS:
            raise ValueError(
                f"{DEPOSIT_CSV} does not have the columns {','.join(DEPOSIT_COLUMNS)}")
        rows = []
        for cells in reader:
            if not cells:
                continue
            if len(cells) != len(DEPOSIT_COLUMNS):
                raise ValueError(f"{DEPOSIT_CSV} has a row of {len(cells)} cells")
            rows.append(dict(zip(DEPOSIT_COLUMNS, cells)))
    except csv.Error as e:
        raise ValueError(f"{DEPOSIT_CSV} is not readable CSV ({e})") from e
    return rows


def _linked(rel):
    """The first component of a package path that is a symbolic link, or None."""
    parts = rel.split("/")
    for depth in range(1, len(parts) + 1):
        if os.path.islink(os.path.join(PKG, *parts[:depth])):
            return "/".join(parts[:depth])
    return None


def _cell_problem(cell, packaged):
    """Why a deposit.csv file cell is not one the package could have written, or None."""
    parts = cell.split("/")
    ok = False
    for root in OWNED_ROOTS:
        prefix = root.split("/")
        if (len(parts) == len(prefix) + 2 and parts[:len(prefix)] == prefix
                and parts[-2] in packaged and PLAIN_NAME_RE.fullmatch(parts[-1])):
            ok = True
    if not ok:
        return ("not " + ", ".join(r + "/" for r in OWNED_ROOTS)
                + " followed by a packaged run and a plain file name")
    link = _linked(cell)
    return f"{link} is a symbolic link" if link else None


def _sha256_and_size(path):
    digest = hashlib.sha256()
    size = 0
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def _entries(rel_dir):
    """The files and links under a package folder (links never followed), as package paths."""
    out = []
    for dirpath, dirnames, filenames in os.walk(_pkg_path(rel_dir)):
        for name in dirnames + filenames:
            path = os.path.join(dirpath, name)
            if name in filenames or os.path.islink(path):
                out.append(os.path.relpath(path, PKG).replace(os.sep, "/"))
    return sorted(out)


def _workspace_runs():
    """The runs of the workspace around the package (each runs/<id>/ with a spec.json)."""
    runs = os.path.join(WS, "runs")
    if not os.path.isdir(runs):
        return set()
    return {n for n in os.listdir(runs) if os.path.isfile(os.path.join(runs, n, "spec.json"))}


def deposit_problems(rows):
    """(problems, notes) of the hash and inventory checks over the deposit.csv rows."""
    problems, notes = [], []
    packaged = {r["run"] for r in rows}
    listed = {r["file"]: r for r in rows if r["file"]}
    for rel, row in sorted(listed.items()):
        reason = _cell_problem(rel, packaged)
        if reason:
            problems.append(f"{DEPOSIT_CSV} row file {rel!r}: {reason}")
            continue
        path = _pkg_path(rel)
        if not os.path.isfile(path):
            problems.append(f"{rel} is listed in {DEPOSIT_CSV} but missing")
            continue
        sha, size = _sha256_and_size(path)
        if sha != row["sha256"]:
            problems.append(f"{rel}: its SHA-256 {sha} differs from the one {DEPOSIT_CSV} "
                            f"gives, {row['sha256'] or '(empty)'}")
        if str(size) != row["bytes"]:
            problems.append(f"{rel}: {size} bytes, {DEPOSIT_CSV} says {row['bytes'] or '(empty)'}")
    root = _pkg_path(PROTOCOL_ROOT)
    if os.path.islink(root):
        problems.append(f"{PROTOCOL_ROOT} is a symbolic link")
    elif os.path.isdir(root):
        for child in sorted(os.listdir(root)):
            path = os.path.join(root, child)
            if child not in packaged or os.path.islink(path) or not os.path.isdir(path):
                problems.append(f"{PROTOCOL_ROOT}/{child} is not the folder of a packaged run")
                continue
            problems.extend(f"{rel} is not in {DEPOSIT_CSV}"
                            for rel in _entries(f"{PROTOCOL_ROOT}/{child}") if rel not in listed)
    workspace_runs = _workspace_runs()
    for folder in ("02_data", "05_inputs"):
        base = _pkg_path(folder)
        if os.path.islink(base) or not os.path.isdir(base):
            continue
        for child in sorted(os.listdir(base)):
            path = os.path.join(base, child)
            if not (os.path.isdir(path) or os.path.islink(path)):
                continue                       # claims_all.csv, README.md: not a run folder
            where = f"{folder}/{child}"
            if child in packaged:
                if os.path.islink(path):
                    problems.append(f"{where} is a symbolic link")
                    continue
                problems.extend(f"{rel} is not in {DEPOSIT_CSV}"
                                for rel in _entries(where) if rel not in listed)
            elif child in workspace_runs:
                problems.append(f"{where} belongs to run '{child}', which is not packaged")
            else:
                notes.append(f"{where} is named after no packaged run; it ships unchecked")
    return problems, notes


def _normalised(tex):
    for pattern in URL_MASK_RES:
        tex = pattern.sub(" ", tex)
    return tex.replace("\\_", "_")


def _names_a_file(path):
    return FILE_WITH_EXTENSION_RE.fullmatch(path.rsplit("/", 1)[-1]) is not None


def _protocol_name(row):
    """The name of a protocol or amendment row's file (or the name it would have)."""
    if row["file"]:
        return row["file"].rsplit("/", 1)[-1]
    m = _PROTOCOL_DESCRIPTION_RE.match(row["description"])
    if m:
        return f"protocol-v{m.group(1)}.json"
    m = _AMENDMENT_DESCRIPTION_RE.match(row["description"])
    return f"amendment-v{m.group(1)}.json" if m else ""


def name_problems(docs, rows):
    """The package names check, from deposit.csv: every path from 02_data/, 05_inputs/ or
    06_provenance/ exists in the package (a path into the protocol folder of a run that
    withholds its protocol fails saying so); a per-run deposit/ path fails, naming the package
    path its row maps to; a bare protocol file name is the name of a file under some
    06_provenance/protocol/<run>/."""
    withheld, withheld_names = {}, {}
    mapped = {"manifest.csv": [DEPOSIT_CSV]}
    for row in rows:
        if row["kind"] in ("protocol", "amendment") and not row["file"] \
                and _WITHHELD in row["description"]:
            withheld.setdefault(row["run"], row["description"].split(_WITHHELD, 1)[1])
            withheld_names.setdefault(row["run"], set()).add(_protocol_name(row).lower())
        for root, folder in PER_RUN_FOLDER.items():
            if row["file"].startswith(root + "/"):
                name = row["file"].rsplit("/", 1)[-1]
                mapped.setdefault(f"{folder}/{name}", []).append(row["file"])
    root = _pkg_path(PROTOCOL_ROOT)
    protocol_names = set()
    if os.path.isdir(root):
        for child in os.listdir(root):
            if os.path.isdir(os.path.join(root, child)):
                protocol_names.update(
                    n for n in os.listdir(os.path.join(root, child))
                    if os.path.isfile(os.path.join(root, child, n)))
    fails = []
    for doc, tex in docs.items():
        text = _normalised(tex)
        for match in PACKAGE_PATH_RE.finditer(text):
            path = match.group(0).rstrip(TRAILING)
            parts = path.split("/")
            if ".." not in parts and os.path.exists(_pkg_path(path)):
                continue
            rid = parts[2] if path.startswith(PROTOCOL_ROOT + "/") and len(parts) > 2 else None
            if rid in withheld:
                fails.append(
                    f"{doc} names {path}, but the protocol of run '{rid}' is withheld "
                    f"({withheld[rid]}): no protocol file of it ships with the package")
            else:
                fails.append(f"{doc} names {path}, which the package does not hold")
        for match in DEPOSIT_PATH_RE.finditer(text):
            path = match.group(0).rstrip(TRAILING)
            rel = path[len("deposit/"):]
            if not _names_a_file(rel):
                continue
            targets = mapped.get(rel)
            where = (f"in the package it is {' or '.join(targets)}" if targets
                     else "the package holds no such file")
            fails.append(f"{doc} names {path}, a path of a per-run paper; {where}")
        for match in BARE_PROTOCOL_RE.finditer(text):
            token = match.group(0)
            if token in protocol_names:
                continue
            runs = sorted(rid for rid, names in withheld_names.items()
                          if token.lower() in names)
            if runs:
                fails.append(
                    f"{doc} names {token}, but the protocol of run(s) {', '.join(runs)} is "
                    "withheld: no such file ships with the package")
            else:
                fails.append(
                    f"{doc} names {token}, which is the name of no file under "
                    f"{PROTOCOL_ROOT}/<run>/")
    return fails


def check_deposit():
    """The deposited files: hashes, inventory and the names rule. Returns ok."""
    if not (os.path.lexists(_pkg_path(DEPOSIT_CSV)) or os.path.lexists(_pkg_path(PROTOCOL_ROOT))
            or has_deposit_trace()):
        print(f"[deposit] no {DEPOSIT_CSV}: the package was assembled before its runs' "
              "protocol files shipped with it; deposit files not checked")
        return True
    try:
        rows = read_deposit_rows()
    except ValueError as e:
        print(f"[deposit] FAIL {e}")
        return False
    if rows is None:
        print(f"[deposit] FAIL {DEPOSIT_CSV} is missing (re-assemble the package)")
        return False
    problems, notes = deposit_problems(rows)
    docs = {}
    for name in ("main.tex", "si.tex"):
        text = _read(f"01_manuscript/{name}")
        if text is not None:
            docs[name] = text
    problems.extend(name_problems(docs, rows))
    for line in problems:
        print(f"[deposit] FAIL {line}")
    for line in notes:
        print(f"[deposit] note: {line}")
    if not problems:
        shipped = sum(1 for r in rows if r["file"])
        print(f"[deposit] {shipped} file(s) listed in {DEPOSIT_CSV}: SHA-256 and sizes match, "
              "no file is unlisted, and every package path the manuscript names exists")
    print(f"[deposit] not checked here: whether {DEPOSIT_CSV} lists the rows the record "
          "under runs/ calls for, whether each run's protocol digest matches run_index.csv, "
          "and the file-name rules of the declaration (run the package gate on the "
          "workspace for those)")
    return not problems


def main():
    ok = True
    main_tex, t_ok = check_tex(os.path.join(MAN, "main.tex"))
    ok = ok and t_ok
    _, s_ok = check_tex(os.path.join(MAN, "si.tex"), check_figs=False)
    ok = ok and s_ok
    ok = check_citations(main_tex) and ok
    ok = check_toolvocab(os.path.join(MAN, "main.tex")) and ok
    ok = check_toolvocab(os.path.join(MAN, "si.tex")) and ok
    ok = check_deposit() and ok
    print("=" * 50)
    print("PACKAGE CHECK:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
