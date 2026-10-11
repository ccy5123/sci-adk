#!/usr/bin/env python3
"""Assemble the package's deterministic RECORD artifact (06_provenance/record.tex).

Field-agnostic: every run, hypothesis, status, recorded point statistic and pre-registered
comparison/threshold, and the record digest (via a read-only audit) are pulled straight from
``runs/<id>/`` -- NOTHING about the science is hardcoded. The run list is DISCOVERED from
``runs/`` (sorted by id), so the same script serves any workspace and any field.

No new belief: this is the deterministic record dump; it asserts no value the record does not
already hold. SPEC-SI-AUTHORING-001 M5 (REQ-SA-505/506): the dump is the package RECORD and is
written to ``06_provenance/record.tex`` (the provenance floor, symmetric to the per-run
``runs/<id>/record.tex``), NOT to ``01_manuscript/si.tex`` -- that slot is now the AUTHORED
package SI (a sibling of the authored ``main.tex``). The record is presented as the record/
provenance, not as a "Supporting Information" sibling of the manuscript. Because it lives outside
the scanned ``01_manuscript/`` dir it is EXEMPT from the package tool-vocab gate BY CONSTRUCTION
(REQ-SA-507), so it may legitimately name provenance (capability/docker/environment).

Narrative grouping (optional): if ``package/narrative.json`` is present, it supplies
author-controlled metadata that groups the runs into the paper's narrative -- a JSON object::

    {
      "title": "Supporting Information: <paper title>",
      "author": "<author>",
      "runs": [
        {"id": "<run-id>", "label": "<one-line description>", "section": "<group>"},
        ...
      ]
    }

The ``runs`` list orders + describes the runs and assigns each to a section group (a paper
narrative band). A run NOT listed is appended, ungrouped, in record (id) order; if no
``narrative.json`` exists, ALL runs are dumped ungrouped in id order. The grouping asserts no
number -- it is presentation only. This is the generic, record-derived-or-config-driven
replacement for any hardcoded cycle map.

Protocol history: for each run, every frozen version of its protocol and the receipt of each
amendment, with the time stated in the file, the SHA-256 of its bytes and the run's protocol
digest -- computed here with the standard library only, from ``runs/<id>/spec.json``,
``spec_history/`` and ``checkpoints/amendment-v<N>.json``. ``06_provenance/deposit.csv``
lists the same files and names this record wherever it prints a checksum. As sci-adk does,
a protocol file or folder that is a symbolic link is refused, and so is a ``spec.json``
whose version lies more than 10 versions past the files that account for it.

Declared data files: for each run, each file its declaration (``runs/<id>/deposit.json``)
declares ``recorded`` or ``external``, under the Evidence item it is declared against, with
the SHA-256 of its bytes -- so ``deposit.csv``'s ``evidence`` column resolves here.

Self-contained: paths are resolved from this file's location
(package/04_scripts/make_si.py -> workspace root), so ``python3 04_scripts/make_si.py`` run
from the package regenerates 06_provenance/record.tex against the workspace record.
"""
import glob
import hashlib
import json
import os
import re
import stat
import unicodedata
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))   # package/04_scripts
PKG = os.path.dirname(HERE)                          # package
WS = os.path.dirname(PKG)                            # workspace root
RUNS = os.path.join(WS, "runs")
# SPEC-SI-AUTHORING-001 M5 (REQ-SA-505): the record artifact relocates to the provenance floor.
OUT = os.path.join(PKG, "06_provenance", "record.tex")
NARRATIVE = os.path.join(PKG, "narrative.json")

BASIS = re.compile(r"'point'=([-\d.eE]+)\s*(<=|>=|<|>|==)\s*([-\d.eE]+)")
SY = {"supported": "S", "refuted": "R", "contested": "C", "proposed": "P"}


# -- escaping: the rules sci-adk's renderer applies ------------------------------------------
# A self-contained copy of sci_adk.render.paper._latex_sanitize and _one_line: this script runs
# from a shipped package where sci-adk need not be installed, and the record must not change
# with the environment that builds it. Every text the record prints -- the title, the author,
# run ids, labels, groups, outcomes, protocol and data descriptions -- goes through tex(): line
# ends normalized, control characters removed, whitespace collapsed to one line (each sits in a
# macro argument or a table cell, where a blank line stops pdflatex), the LaTeX specials
# escaped, and every other non-ASCII character mapped, kept or folded as render does (a
# character with no form prints as "?"). sci-adk's test suite compares tex() with the
# renderer over a broad sample.
_TEX_SPECIAL = {
    '\\': r'\textbackslash{}',
    '&': r'\&',
    '%': r'\%',
    '$': r'\$',
    '#': r'\#',
    '_': r'\_',
    '{': r'\{',
    '}': r'\}',
    '~': r'\textasciitilde{}',
    '^': r'\textasciicircum{}',
}
# Curated Unicode -> LaTeX (sci_adk.render.paper._UNICODE_MAP).
_UNICODE_MAP = {
    '₀': '$_0$', '₁': '$_1$', '₂': '$_2$', '₃': '$_3$',
    '₄': '$_4$', '₅': '$_5$', '₆': '$_6$', '₇': '$_7$',
    '₈': '$_8$', '₉': '$_9$', '⁰': '$^0$', '¹': '$^1$',
    '²': '$^2$', '³': '$^3$', '⁴': '$^4$', '⁵': '$^5$',
    '⁶': '$^6$', '⁷': '$^7$', '⁸': '$^8$', '⁹': '$^9$',
    '⁺': '$^+$', '⁻': '$^-$', 'ⁿ': '$^n$', '≥': r'$\geq$',
    '≤': r'$\leq$', '≠': r'$\neq$', '±': r'$\pm$', '×': r'$\times$',
    '÷': r'$\div$', '−': '$-$', '≈': r'$\approx$', '≡': r'$\equiv$',
    '∝': r'$\propto$', '·': r'$\cdot$', '∙': r'$\cdot$', '∞': r'$\infty$',
    '∑': r'$\sum$', '∏': r'$\prod$', '∫': r'$\int$', '√': r'$\surd$',
    '∂': r'$\partial$', '∇': r'$\nabla$', '∈': r'$\in$', '∉': r'$\notin$',
    '⊂': r'$\subset$', '⊆': r'$\subseteq$', '∪': r'$\cup$', '∩': r'$\cap$',
    '→': r'$\rightarrow$', '←': r'$\leftarrow$', '↔': r'$\leftrightarrow$', '⇒': r'$\Rightarrow$',
    '⇐': r'$\Leftarrow$', 'α': r'$\alpha$', 'β': r'$\beta$', 'γ': r'$\gamma$',
    'δ': r'$\delta$', 'ε': r'$\epsilon$', 'ζ': r'$\zeta$', 'η': r'$\eta$',
    'θ': r'$\theta$', 'ι': r'$\iota$', 'κ': r'$\kappa$', 'λ': r'$\lambda$',
    'μ': r'$\mu$', 'ν': r'$\nu$', 'ξ': r'$\xi$', 'ο': 'o',
    'π': r'$\pi$', 'ρ': r'$\rho$', 'σ': r'$\sigma$', 'ς': r'$\varsigma$',
    'τ': r'$\tau$', 'υ': r'$\upsilon$', 'φ': r'$\phi$', 'χ': r'$\chi$',
    'ψ': r'$\psi$', 'ω': r'$\omega$', 'Γ': r'$\Gamma$', 'Δ': r'$\Delta$',
    'Θ': r'$\Theta$', 'Λ': r'$\Lambda$', 'Ξ': r'$\Xi$', 'Π': r'$\Pi$',
    'Σ': r'$\Sigma$', 'Φ': r'$\Phi$', 'Ψ': r'$\Psi$', 'Ω': r'$\Omega$',
    'µ': r'$\mu$', '°': r'\textdegree{}', '–': '--', '—': '---',
    '‘': '`', '’': "'", '“': '``', '”': "''",
    '…': r'\ldots{}',
}
# Latin-1 Supplement + Latin Extended-A pass through inputenc, except the letters with no
# glyph (sci_adk.render.paper._ACCENT_LO/_ACCENT_HI/_UNDEFINED_LATIN_A).
_ACCENT_LO = 0x00C0
_ACCENT_HI = 0x017E
_UNDEFINED_LATIN_A = frozenset('ĦħĸĿŀŉŦŧ')
_UNICODE_PLACEHOLDER = "?"
# C0 controls other than tab and line feed, and DEL: pdflatex stops on each.
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


def _clean_text(s):
    return _CONTROL_RE.sub("", s.replace("\r\n", "\n").replace("\r", "\n"))


def _one_line(s):
    return " ".join(_clean_text(s).split())


def _escape(s):
    return "".join(_TEX_SPECIAL.get(ch, ch) for ch in s)


def _sanitize(s):
    out = []
    for ch in _escape(_clean_text(s)):
        if ord(ch) < 0x80:
            out.append(ch)
        elif ch in _UNICODE_MAP:
            out.append(_UNICODE_MAP[ch])
        elif _ACCENT_LO <= ord(ch) <= _ACCENT_HI and ch not in _UNDEFINED_LATIN_A:
            out.append(ch)
        else:  # NFKD fold: ASCII fallout escaped, combining marks dropped, the rest "?"
            for f in unicodedata.normalize("NFKD", ch):
                if ord(f) < 0x80:
                    out.append(_escape(f))
                elif not unicodedata.combining(f):
                    out.append(_UNICODE_PLACEHOLDER)
    return "".join(out)


def tex(s):
    """``s`` as the record prints it: on one line and escaped as sci-adk's renderer escapes
    text (see the comment above)."""
    return _sanitize(_one_line(str(s)))


def discover_runs():
    """Every ``runs/<id>/`` holding a spec.json, sorted by id (field-agnostic)."""
    out = []
    for d in sorted(glob.glob(os.path.join(RUNS, "*"))):
        if os.path.isfile(os.path.join(d, "spec.json")):
            out.append(os.path.basename(d))
    return out


def load_narrative():
    """Author-controlled narrative metadata, or empty defaults (graceful omission)."""
    if not os.path.exists(NARRATIVE):
        return {"title": None, "author": None, "runs": []}
    with open(NARRATIVE) as fh:
        n = json.load(fh)
    n.setdefault("title", None)
    n.setdefault("author", None)
    n.setdefault("runs", [])
    return n


def ordered_runs(discovered, narrative_runs):
    """Order/label/section the runs: narrative order first, then any unlisted run by id.

    Returns a list of (run_id, label, section) -- ``section`` is None for ungrouped runs.
    A narrative entry naming a run absent from the record is dropped (the record wins).
    """
    seen = set()
    out = []
    for entry in narrative_runs:
        rid = entry.get("id")
        if rid in discovered and rid not in seen:
            out.append((rid, entry.get("label", rid), entry.get("section")))
            seen.add(rid)
    for rid in discovered:
        if rid not in seen:
            out.append((rid, rid, None))
            seen.add(rid)
    return out


def claims(rid):
    out = []
    for cj in sorted(glob.glob(os.path.join(RUNS, rid, "claims", "claim-*.json"))):
        with open(cj) as fh:
            d = json.load(fh)
        b = (d.get("confidence", {}) or {}).get("basis", "") or ""
        m = BASIS.search(b)
        pt, op, th = (m.group(1), m.group(2), m.group(3)) if m else ("--", "", "--")
        out.append((d.get("answers", d.get("id", "")), d.get("status", ""), pt, op, th))
    return out


def digest(rid):
    """The 12-char record digest from the read-only audit (in-process; CLI fallback)."""
    try:
        from pathlib import Path

        from sci_adk.loop.verify import verify_run

        return verify_run(Path(os.path.join(RUNS, rid))).digest[:12]
    except Exception:
        return _digest_via_cli(rid)


def _digest_via_cli(rid):
    import subprocess

    try:
        r = subprocess.run(
            ["sci-adk", "verify", os.path.join(RUNS, rid)],
            capture_output=True, text=True, timeout=120,
        )
        m = re.search(r"record digest \(sha256\):\s*([0-9a-f]+)", r.stdout)
        return m.group(1)[:12] if m else "n/a"
    except Exception:
        return "n/a"


def _read_json_bytes(data):
    try:
        payload = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _when(value):
    """A recorded time as an aware UTC datetime, or None (naive times are read as UTC)."""
    if not isinstance(value, str):
        return None
    try:
        t = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return t if t.tzinfo is not None else t.replace(tzinfo=timezone.utc)


def _from_timestamp(value):
    try:
        return datetime.fromtimestamp(float(value), tz=timezone.utc)
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def _fmt_time(t):
    return "time unknown" if t is None else t.astimezone(timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ")


# How many of versions 1..V (V: the version spec.json states) may have no file accounting for
# them (sci_adk.render.deposit.VERSION_MARGIN); past it spec.json is not what sci-adk wrote.
VERSION_MARGIN = 10
_HISTORY_NAME_RE = re.compile(r"spec\.v([1-9][0-9]{0,8})\.json")
_RECEIPT_NAME_RE = re.compile(r"amendment-v([1-9][0-9]{0,8})\.json")


def _plain_folder(run_dir, name):
    """Refuse a protocol folder of the run that is a symbolic link or not a folder."""
    path = os.path.join(run_dir, name)
    try:
        st = os.lstat(path)
    except FileNotFoundError:
        return
    if stat.S_ISLNK(st.st_mode) or not stat.S_ISDIR(st.st_mode):
        raise ValueError(f"{path} is a symbolic link or not a folder; protocol files are read "
                         "only from plain folders")


def _protocol_bytes(run_dir, rel):
    """The bytes of a protocol file of the run, or None when there is none. Never read through
    a symbolic link: a link, or anything but a plain file, is refused (ValueError)."""
    path = os.path.join(run_dir, rel)
    try:
        st = os.lstat(path)
    except FileNotFoundError:
        return None
    if stat.S_ISLNK(st.st_mode) or not stat.S_ISREG(st.st_mode):
        raise ValueError(f"{path} is a symbolic link or not a plain file; protocol files are "
                         "read only as plain files")
    with open(path, "rb") as fh:
        return fh.read()


def _numbers_on_disk(folder, pattern):
    if not os.path.isdir(folder):
        return []
    return [int(m.group(1)) for m in (pattern.fullmatch(n) for n in os.listdir(folder)) if m]


def _check_version_bound(run_dir, version):
    """Refuse a version with more than VERSION_MARGIN of versions 1..version that no file of
    the run accounts for (its history file, the receipt that produced it or replaced it, or
    spec.json itself)."""
    history = _numbers_on_disk(os.path.join(run_dir, "spec_history"), _HISTORY_NAME_RE)
    receipts = _numbers_on_disk(os.path.join(run_dir, "checkpoints"), _RECEIPT_NAME_RE)
    accounted = {version} | set(history) | set(receipts) | {n - 1 for n in receipts}
    missing = version - len({n for n in accounted if 1 <= n <= version})
    if missing > VERSION_MARGIN:
        raise ValueError(f"{run_dir}/spec.json says version {version}, but no file accounts "
                         f"for {missing} of versions 1 to {version}")


def protocol_history(run_dir):
    """The run's protocol files in the order they were written, and its protocol digest.

    Returns ``(entries, digest)``: ``entries`` is a list of ``(name, description, time label,
    sha256)`` -- version 1, then each amendment receipt followed by the version it produced;
    ``sha256`` is empty for a version whose file was not kept, whose time is the one the next
    version records for it (``prior_version_id``). ``digest`` is the SHA-256 of the listing
    ``sha256sum`` prints for the kept files under these names, names in byte order. Every time
    comes from a local clock.

    Raises ValueError for a protocol file or folder that is a symbolic link, and for a version
    more than VERSION_MARGIN versions past the files on disk (as sci-adk refuses them).
    """
    for folder in ("spec_history", "checkpoints"):
        _plain_folder(run_dir, folder)
    current = _protocol_bytes(run_dir, "spec.json")
    if current is None:
        raise ValueError(f"{run_dir}/spec.json does not exist")
    version = int(json.loads(current.decode("utf-8")).get("version", 1))
    if version < 1:
        raise ValueError(f"{run_dir}/spec.json has version {version}")
    _check_version_bound(run_dir, version)
    versions = {}
    for n in range(1, version):
        data = _protocol_bytes(run_dir, f"spec_history/spec.v{n}.json")
        if data is not None:
            versions[n] = data
    versions[version] = current
    receipts = {}
    for n in range(2, version + 1):
        data = _protocol_bytes(run_dir, f"checkpoints/amendment-v{n}.json")
        if data is not None:
            receipts[n] = data
    payloads = {n: _read_json_bytes(data) for n, data in versions.items()}

    def sha(data):
        return hashlib.sha256(data).hexdigest()

    entries = []
    for n in range(1, version + 1):
        if n in receipts:
            t = _when(_read_json_bytes(receipts[n]).get("recorded_at"))
            entries.append((f"amendment-v{n}.json", f"amendment that produced version {n}",
                            f"recorded {_fmt_time(t)}", sha(receipts[n])))
        t = _when(payloads[n].get("created_at")) if n in payloads else None
        if t is None and n + 1 in payloads:
            t = _from_timestamp(payloads[n + 1].get("prior_version_id"))
        if n == version:
            description = f"protocol, version {n} (current)"
        elif n in versions:
            description = f"protocol, version {n}, replaced by version {n + 1}"
        else:
            description = f"protocol, version {n}; file not kept"
        entries.append((f"protocol-v{n}.json", description, f"created {_fmt_time(t)}",
                        sha(versions[n]) if n in versions else ""))
    listing = "".join(
        f"{entry[3]}  {entry[0]}\n" for entry in sorted(entries) if entry[3]
    )
    return entries, hashlib.sha256(listing.encode("utf-8")).hexdigest()


def protocol_section(runs):
    """The record's "Protocol history" section: one block per run (in index order)."""
    L = [r"\section{Protocol history}"]
    L.append(
        r"For each run, every frozen version of its protocol and the receipt of each "
        r"amendment, in the order they were written, with the time stated in the file and "
        r"the SHA-256 of the file's bytes. The times come from local clocks; nothing "
        r"witnesses them. \texttt{06\_provenance/deposit.csv} lists the same files; those "
        r"a run ships are in the folder named after it under "
        r"\texttt{06\_provenance/protocol/}. A run's protocol digest is the SHA-256 of the "
        r"listing \texttt{sha256sum} prints for its files that were kept, names in byte "
        r"order."
    )
    for rid, _label, _section in runs:
        L.append(r"\subsection*{Run \texttt{" + tex(rid) + r"}}")
        try:
            entries, digest = protocol_history(os.path.join(RUNS, rid))
        except (OSError, ValueError, AttributeError, TypeError):
            L.append(r"\emph{The protocol files of this run could not be read.}")
            continue
        L.append(r"\begin{description}")
        for name, description, when, sha in entries:
            checksum = ("SHA-256:\\\\\n    {\\small\\texttt{" + sha + "}}") if sha else "no SHA-256"
            # "created <time>" / "recorded <time>": the time in an \mbox, so a line never
            # breaks at one of its hyphens (as the per-run record.tex sets it).
            verb, _, at = when.partition(" ")
            L.append(r"  \item[\texttt{" + tex(name) + r"}] " + tex(description) + "; "
                     + tex(verb) + r" \mbox{" + tex(at) + "}; " + checksum)
        L.append(r"\end{description}")
        L.append("\\noindent Protocol digest:\\\\\n{\\small\\texttt{" + digest + "}}")
    return L


# The declared origins whose bytes the record fixes (sci_adk.core.deposit: recorded study data
# and external third-party data); a derived file carries no checksum claim.
DECLARED_ORIGINS = ("recorded", "external")


def _source_sha256(run_dir, source):
    """The SHA-256 of a declared ``source`` -- looked up in the run's folder, then the
    workspace, as sci-adk looks it up -- or "" when it is not a readable file there."""
    if not isinstance(source, str) or not source or os.path.isabs(source) \
            or ".." in source.replace("\\", "/").split("/"):
        return ""
    for root in (run_dir, WS):
        path = os.path.join(root, source)
        if os.path.isfile(path):
            digest = hashlib.sha256()
            try:
                with open(path, "rb") as fh:
                    for chunk in iter(lambda: fh.read(1 << 20), b""):
                        digest.update(chunk)
            except OSError:
                return ""
            return digest.hexdigest()
    return ""


def declared_files(rid):
    """``[(Evidence id, description, SHA-256)]`` of each ``recorded`` or ``external`` entry of
    the run's declaration (``runs/<id>/deposit.json``), in declaration order; ``[]`` when the
    run has none. The SHA-256 is "" for a source that cannot be read."""
    run_dir = os.path.join(RUNS, rid)
    path = os.path.join(run_dir, "deposit.json")
    if not os.path.isfile(path):
        return []
    with open(path, encoding="utf-8") as fh:
        payload = json.load(fh)
    out = []
    for entry in payload.get("files") or []:
        if isinstance(entry, dict) and entry.get("origin") in DECLARED_ORIGINS:
            out.append((str(entry.get("evidence") or ""), str(entry.get("description") or ""),
                        _source_sha256(run_dir, entry.get("source"))))
    return out


def declared_files_section(runs):
    """The record's "Declared data files" section (one block per run that declares a recorded
    or external file, in index order), or ``[]`` when no run does."""
    blocks = []
    for rid, _label, _section in runs:
        try:
            files = declared_files(rid)
        except (OSError, ValueError, AttributeError, TypeError):
            blocks.append((rid, None))
            continue
        if files:
            blocks.append((rid, files))
    if not blocks:
        return []
    L = [r"\section{Declared data files}"]
    L.append(
        r"For each run, each declared file whose bytes the record fixes (a table of the "
        r"study declared as recorded, or a third-party file), under the Evidence item declared "
        r"to hold its SHA-256, with that SHA-256. "
        r"\texttt{06\_provenance/deposit.csv} lists the same files with their terms (its "
        r"\texttt{evidence} column names the item); those a run ships are in the folder named "
        r"after it under \texttt{02\_data/} or \texttt{05\_inputs/}. A derived file is not "
        r"listed: nothing in the record fixes its bytes."
    )
    for rid, files in blocks:
        L.append(r"\subsection*{Run \texttt{" + tex(rid) + r"}}")
        if files is None:
            L.append(r"\emph{The declaration of this run could not be read.}")
            continue
        L.append(r"\begin{description}")
        for evidence, description, sha in files:
            checksum = (("SHA-256:\\\\\n    {\\small\\texttt{" + sha + "}}") if sha
                        else "Its file could not be read.")
            sentence = description.strip()
            if sentence and not sentence.endswith("."):
                sentence += "."
            L.append(r"  \item[\texttt{" + tex(evidence) + r"}] "
                     + (tex(sentence) + " " if sentence else "") + checksum)
        L.append(r"\end{description}")
    return L


def build():
    discovered = discover_runs()
    narrative = load_narrative()
    runs = ordered_runs(discovered, narrative.get("runs", []))

    idx_rows = []        # (run_id, label, section, n_hyp, verdicts, digest)
    claim_blocks = {}
    total_claims = 0
    for rid, label, section in runs:
        cs = claims(rid)
        dg = digest(rid)
        cnt = {}
        for _, st, _, _, _ in cs:
            cnt[st] = cnt.get(st, 0) + 1
        verd = "/".join(f"{n}{SY.get(k, k[:1].upper())}" for k, n in sorted(cnt.items()))
        idx_rows.append((rid, label, section, len(cs), verd, dg))
        claim_blocks[rid] = cs
        total_claims += len(cs)

    title = narrative.get("title") or r"Deterministic record"
    author = narrative.get("author") or r"sci-adk (deterministic record dump)"

    L = []
    L.append(r"\documentclass[10pt]{article}")
    # T1 + Latin Modern, as in every preamble sci-adk emits: in the default OT1 encoding
    # letters such as Ð, þ, Ę and the guillemets stop pdflatex.
    L.append(r"\usepackage[T1]{fontenc}")
    L.append(r"\usepackage{lmodern}")
    L.append(r"\usepackage[margin=1in]{geometry}")
    L.append(r"\usepackage{booktabs}\usepackage{longtable}")
    L.append(r"\usepackage[hidelinks]{hyperref}")
    L.append(r"\title{" + tex(title) + r"}")
    L.append(r"\author{" + tex(author) + r"}\date{}")
    L.append(r"\begin{document}\maketitle")
    L.append(r"\section{Overview}")
    # M5 (REQ-SA-506): this is the package RECORD, presented as the record/provenance -- not as
    # a "Supporting Information" sibling of the manuscript (that slot is the authored si.tex).
    # The record lives in 06_provenance/ and is EXEMPT from the tool-vocab gate by construction
    # (REQ-SA-507), but the prose still reads as the science.
    L.append(
        r"This is the deterministic record behind the main paper. "
        r"Each run fixed a pre-registered protocol (its hypotheses and the acceptance "
        r"criterion for each) in advance, ran a deterministic analysis that recorded its "
        r"result (null and negative results included), and reached a per-hypothesis outcome "
        r"under the pre-specified criterion. Every value below is a recorded result that an "
        r"automated read-only audit re-derives from its archived inputs; nothing here is "
        r"asserted that the record does not already hold. Tables~\ref{tab:index} "
        r"and~\ref{tab:claims} are generated directly from the archive "
        r"(\texttt{04\_scripts/make\_si.py})."
    )

    # Index table -- run id, hypothesis count, verdicts, record digest, with optional
    # section-group banners (omitted gracefully when a run has no narrative section).
    L.append(r"\begin{longtable}{llrll}")
    L.append(
        r"\caption{Run index: run identifier, number of hypotheses, outcomes (S supported, "
        r"R refuted, C contested, P proposed), and record digest.}"
        r"\label{tab:index}\\"
    )
    L.append(r"\toprule run id & description & hyp & outcomes & digest \\ "
             r"\midrule \endfirsthead")
    L.append(r"\toprule run id & description & hyp & outcomes & digest \\ "
             r"\midrule \endhead")
    cur = object()  # sentinel so the first section (even None) prints once if grouped
    any_section = any(sec for _, _, sec, _, _, _ in idx_rows)
    for rid, label, section, nh, verd, dg in idx_rows:
        if any_section and section != cur:
            cur = section
            banner = tex(section) if section else r"(ungrouped)"
            L.append(r"\multicolumn{5}{l}{\textit{" + banner + r"}}\\")
        L.append(f"\\texttt{{{tex(rid)}}} & {tex(label)} & {nh} & {tex(verd)} & "
                 f"\\texttt{{{tex(dg)}}} \\\\")
    L.append(r"\bottomrule\end{longtable}")

    # Claims table -- the deterministic point statistic + pre-registered op/threshold/verdict.
    L.append(r"\begin{longtable}{lllll}")
    L.append(
        r"\caption{Per-hypothesis recorded statistics: the deterministic point statistic, "
        r"the pre-registered comparison and threshold, and the resulting outcome.}"
        r"\label{tab:claims}\\"
    )
    L.append(r"\toprule hyp & point & op & threshold & status \\ \midrule \endfirsthead")
    L.append(r"\toprule hyp & point & op & threshold & status \\ \midrule \endhead")
    for rid, label, section, nh, verd, dg in idx_rows:
        for hyp, st, pt, op, th in claim_blocks[rid]:
            opx = {"<=": r"$\leq$", ">=": r"$\geq$", "<": r"$<$", ">": r"$>$",
                   "==": r"$=$", "": ""}.get(op, tex(op))
            L.append(f"{tex(hyp)} & {tex(pt)} & {opx} & {tex(th)} & "
                     f"\\textbf{{{tex(SY.get(st, st))}}} \\\\")
    L.append(r"\bottomrule\end{longtable}")

    # Each run's protocol history and protocol digest (design/deposit-files.md D11).
    L.extend(protocol_section(runs))
    # Each declared recorded / external file's Evidence item and SHA-256 (D4: the package's
    # Evidence ids sit beside the record that resolves them).
    L.extend(declared_files_section(runs))

    L.append(r"\section{Reproducibility}")
    L.append(
        r"Each run's directory carries its pre-registered protocol, the recorded results, "
        r"the per-hypothesis outcomes, and a typeset per-run report. An automated, read-only "
        r"audit re-derives every outcome from the archived inputs and confirms the record "
        r"reproduces; the record digests in Table~\ref{tab:index} reproduce. The exact "
        r"reproduction command and per-run digests are listed in the provenance index "
        r"(\texttt{06\_provenance/run\_index.csv}); see the package \texttt{README.md} for "
        r"one-line reproduction of the whole record."
    )

    # M5 (REQ-SA-506a, F2): the "Data & code availability" statement lives in the RECORD body --
    # the AUTHORITATIVE source the deposit-completeness check reads (NOT the README). It is
    # record prose (names where the data/code are deposited); it asserts no measured value (no
    # \evval), so it is number-audit-clean and inside the exempt record artifact (REQ-SA-507).
    L.append(r"\section{Data \& code availability}")
    L.append(
        r"The data and code behind every recorded result are deposited in this package: the "
        r"per-run inputs, official scripts, and figures are in \texttt{04\_scripts/} and "
        r"\texttt{03\_figures/}; the master per-Claim table is "
        r"\texttt{02\_data/claims\_all.csv}; and the full read-only reproduction trail "
        r"(per-run digests and audit logs) is in \texttt{06\_provenance/}. Deposit this "
        r"package to a public archive and cite its identifier for permanent availability."
    )

    L.append(r"\end{document}")

    text = "\n".join(L) + "\n"
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as fh:
        fh.write(text)
    print(f"wrote {OUT}: {len(text)} chars, {len(idx_rows)} runs, {total_claims} claims")


if __name__ == "__main__":
    build()
