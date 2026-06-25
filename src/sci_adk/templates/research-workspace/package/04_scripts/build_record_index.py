#!/usr/bin/env python3
"""Record-driven package index builder (field-agnostic, reusable).

Run inside ANY verify-green sci-adk workspace; it reads only the frozen record
(``runs/<id>/spec.json`` + ``claims/``) plus a read-only ``sci-adk verify``, and emits
two provenance tables. It hardcodes nothing about the science: every column is read from
the record, so the same script serves any workspace and any field.

Outputs (relative to the package dir):
  06_provenance/run_index.csv   one row per run: hypotheses, verdicts, digest, reproduced
  02_data/claims_all.csv        one row per recorded Claim: mode, referent, statistic, rule, status

No new belief is created: statistics and statuses are copied verbatim from the frozen
Claims, and the record digest + reproduction flag come from the read-only audit
(``sci_adk.loop.verify`` when sci-adk is importable, else the ``sci-adk verify`` CLI).

This is a builder the package assembler (``sci_adk.render.package``) invokes; it is also
shipped INTO each workspace package so a reviewer can regenerate the tables from the record
with ``python3 04_scripts/build_record_index.py``.
"""
import argparse
import csv
import glob
import json
import os
import re

# Parse the recorded point-statistic/op/threshold out of a numeric Claim's confidence basis
# (the DecisionEngine writes it verbatim, e.g. "... statistic 'point'=0.72 >= 0.5 ...").
BASIS = re.compile(r"'point'=([-\d.eEnan]+)\s*(<=|>=|<|>|==)\s*([-\d.eEnan]+)")


def load_claims(run_dir):
    rows = []
    for cj in sorted(glob.glob(os.path.join(run_dir, "claims", "claim-*.json"))):
        with open(cj) as fh:
            d = json.load(fh)
        basis = (d.get("confidence", {}) or {}).get("basis", "") or ""
        m = BASIS.search(basis)
        point, op, thr = (m.group(1), m.group(2), m.group(3)) if m else ("", "", "")
        rows.append({
            "hyp": d.get("answers", d.get("id", "")),
            "status": d.get("status", ""),
            "mode": d.get("mode", ""),
            "point": point, "op": op, "threshold": thr,
            "statement": (d.get("statement", "") or "").replace("\n", " ").strip(),
        })
    return rows


def load_spec_modes(run_dir):
    """hyp_id -> (mode, referent) from the frozen spec."""
    out = {}
    sp = os.path.join(run_dir, "spec.json")
    if os.path.exists(sp):
        with open(sp) as fh:
            spec = json.load(fh)
        for h in spec.get("hypotheses", []):
            out[h.get("id", "")] = (h.get("mode", ""), h.get("referent", ""))
    return out


def verify(run_dir):
    """Return (reproduced: 'yes'|'no'|'n/a', digest12) from the read-only audit.

    Prefers the in-process ``sci_adk.loop.verify`` (deterministic, no subprocess); falls
    back to scraping the ``sci-adk verify`` CLI text only when sci-adk is not importable
    (so the shipped package still regenerates on a machine with just the CLI installed).
    """
    try:
        from pathlib import Path

        from sci_adk.loop.verify import verify_run

        report = verify_run(Path(run_dir))
        repro = "yes" if report.all_reproduced else "no"
        return repro, (report.digest[:12] if report.digest else "n/a")
    except Exception:
        return _verify_via_cli(run_dir)


def _verify_via_cli(run_dir):
    """Fallback: drive the ``sci-adk verify`` CLI and scrape its output."""
    import subprocess

    digest_re = re.compile(r"record digest \(sha256\):\s*([0-9a-f]+)")
    try:
        r = subprocess.run(
            ["sci-adk", "verify", run_dir],
            capture_output=True, text=True, timeout=180,
        )
        out = r.stdout + r.stderr
        repro = "yes" if "all recorded claims reproduced" in out else "no"
        m = digest_re.search(out)
        return repro, (m.group(1)[:12] if m else "n/a")
    except Exception:
        return "n/a", "n/a"


def discover_runs(ws):
    """Every ``runs/<id>/`` holding a spec.json, sorted by id (field-agnostic, no prefix)."""
    runs = sorted(glob.glob(os.path.join(ws, "runs", "*")))
    return [r for r in runs if os.path.isfile(os.path.join(r, "spec.json"))]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", default=".")
    ap.add_argument("--out", default="package")
    args = ap.parse_args()
    ws = os.path.abspath(args.workspace)
    out = os.path.join(ws, args.out)
    runs = discover_runs(ws)

    os.makedirs(os.path.join(out, "06_provenance"), exist_ok=True)
    os.makedirs(os.path.join(out, "02_data"), exist_ok=True)

    idx_path = os.path.join(out, "06_provenance", "run_index.csv")
    cl_path = os.path.join(out, "02_data", "claims_all.csv")

    n_claims = 0
    SY = {"supported": "S", "refuted": "R", "contested": "C", "proposed": "P"}
    with open(idx_path, "w", newline="") as fi, open(cl_path, "w", newline="") as fc:
        iw = csv.writer(fi)
        cw = csv.writer(fc)
        iw.writerow(["run_id", "n_hypotheses", "verdicts", "reproduced",
                     "record_digest_sha256_12"])
        cw.writerow(["run_id", "hyp_id", "mode", "referent", "status",
                     "point_statistic", "op", "threshold", "statement"])
        for run_dir in runs:
            rid = os.path.basename(run_dir)
            claims = load_claims(run_dir)
            modes = load_spec_modes(run_dir)
            repro, dig = verify(run_dir)
            cnt = {}
            for c in claims:
                cnt[c["status"]] = cnt.get(c["status"], 0) + 1
            verd = "/".join(
                f"{n}{SY.get(k, k[:1].upper())}" for k, n in sorted(cnt.items())
            )
            iw.writerow([rid, len(claims), verd, repro, dig])
            for c in claims:
                mode, ref = modes.get(c["hyp"], (c["mode"], ""))
                cw.writerow([rid, c["hyp"], mode or c["mode"], ref, c["status"],
                             c["point"], c["op"], c["threshold"], c["statement"]])
                n_claims += 1

    print(f"wrote {idx_path}: {len(runs)} runs")
    print(f"wrote {cl_path}: {n_claims} claims")


if __name__ == "__main__":
    main()
