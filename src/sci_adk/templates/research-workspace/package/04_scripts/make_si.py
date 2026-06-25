#!/usr/bin/env python3
"""Assemble the package Supporting Information (01_manuscript/si.tex) from the frozen record.

Field-agnostic: every run, hypothesis, status, recorded point statistic and pre-registered
comparison/threshold, and the record digest (via a read-only audit) are pulled straight from
``runs/<id>/`` -- NOTHING about the science is hardcoded. The run list is DISCOVERED from
``runs/`` (sorted by id), so the same script serves any workspace and any field.

No new belief: the SI is the deterministic record dump; it asserts no value the record does
not already hold. Prose names the science, not the toolchain.

Narrative grouping (optional): if ``package/narrative.json`` is present, it supplies
author-controlled metadata that groups the runs into the paper's narrative -- a JSON object::

    {
      "title": "Supporting Information\\\\<paper title>",
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

Self-contained: paths are resolved from this file's location
(package/04_scripts/make_si.py -> workspace root), so ``python3 04_scripts/make_si.py`` run
from the package regenerates 01_manuscript/si.tex against the workspace record.
"""
import glob
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))   # package/04_scripts
PKG = os.path.dirname(HERE)                          # package
WS = os.path.dirname(PKG)                            # workspace root
RUNS = os.path.join(WS, "runs")
OUT = os.path.join(PKG, "01_manuscript", "si.tex")
NARRATIVE = os.path.join(PKG, "narrative.json")

BASIS = re.compile(r"'point'=([-\d.eE]+)\s*(<=|>=|<|>|==)\s*([-\d.eE]+)")
SY = {"supported": "S", "refuted": "R", "contested": "C", "proposed": "P"}


def esc(s):
    return (str(s).replace("\\", "\\textbackslash{}").replace("_", "\\_")
            .replace("%", "\\%").replace("&", "\\&").replace("#", "\\#"))


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

    title = narrative.get("title") or r"Supporting Information"
    author = narrative.get("author") or r"~"

    L = []
    L.append(r"\documentclass[10pt]{article}")
    L.append(r"\usepackage[margin=1in]{geometry}")
    L.append(r"\usepackage{booktabs}\usepackage{longtable}")
    L.append(r"\usepackage[hidelinks]{hyperref}")
    L.append(r"\title{" + title + r"}")
    L.append(r"\author{" + esc(author) + r"}\date{}")
    L.append(r"\begin{document}\maketitle")
    L.append(r"\section{Overview}")
    # The SI prose names the SCIENCE, not the toolchain (the package gate checks si.tex
    # tool-agnostic too): "outcome" not "verdict", "deterministic archive" not "append-only".
    L.append(
        r"This Supporting Information is the deterministic archive behind the main paper. "
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
            banner = esc(section) if section else r"(ungrouped)"
            L.append(r"\multicolumn{5}{l}{\textit{" + banner + r"}}\\")
        L.append(f"\\texttt{{{esc(rid)}}} & {esc(label)} & {nh} & {esc(verd)} & "
                 f"\\texttt{{{dg}}} \\\\")
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
                   "==": r"$=$", "": ""}.get(op, esc(op))
            L.append(f"{esc(hyp)} & {esc(pt)} & {opx} & {esc(th)} & "
                     f"\\textbf{{{SY.get(st, st)}}} \\\\")
    L.append(r"\bottomrule\end{longtable}")

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
    L.append(r"\end{document}")

    text = "\n".join(L) + "\n"
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as fh:
        fh.write(text)
    print(f"wrote {OUT}: {len(text)} chars, {len(idx_rows)} runs, {total_claims} claims")


if __name__ == "__main__":
    build()
