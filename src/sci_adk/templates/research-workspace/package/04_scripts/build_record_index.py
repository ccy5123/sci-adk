#!/usr/bin/env python3
"""Record-driven package index builder (field-agnostic, reusable).

Run inside ANY verify-green sci-adk workspace; it reads only the frozen record
(``runs/<id>/spec.json`` + ``claims/``) plus a read-only ``sci-adk verify``, and emits
two provenance tables. It hardcodes nothing about the science: every column is read from
the record, so the same script serves any workspace and any field.

Outputs (relative to the package dir):
  06_provenance/run_index.csv   one row per run: hypotheses, verdicts, digest, reproduced,
                                protocol digest
  02_data/claims_all.csv        one row per recorded Claim: mode, referent, statistic, rule, status

No new belief is created: statistics and statuses are copied verbatim from the frozen
Claims, and the record digest + reproduction flag come from the read-only audit
(``sci_adk.loop.verify`` when sci-adk is importable, else the ``sci-adk verify`` CLI).
The protocol digest is computed here, with the standard library only, from the run's
protocol files (``spec.json``, ``spec_history/``, ``checkpoints/amendment-v<N>.json``). As
sci-adk does, a protocol file or folder that is a symbolic link is refused, and so is a
``spec.json`` whose version lies more than 10 versions past the files that account for it;
the run's cell then reads ``n/a``.

This is a builder the package assembler (``sci_adk.render.package``) invokes; it is also
shipped INTO each workspace package so a reviewer can regenerate the tables from the record
with ``python3 04_scripts/build_record_index.py``.
"""
import argparse
import csv
import glob
import hashlib
import json
import os
import re
import stat

# Parse the recorded point-statistic/op/threshold out of a numeric Claim's confidence basis
# (the DecisionEngine writes it verbatim, e.g. "... statistic 'point'=0.72 >= 0.5 ...").
# ASCII digits only: without re.ASCII, \d also matches other scripts' digits.
BASIS = re.compile(r"'point'=([-\d.eEnan]+)\s*(<=|>=|<|>|==)\s*([-\d.eEnan]+)", re.ASCII)


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


def protocol_files(run_dir):
    """{name: bytes} of every kept protocol version and amendment receipt of the run.

    The names are the ones the package ships them under (``06_provenance/protocol/<id>/``):
    ``protocol-v<N>.json`` for version N (``spec_history/spec.v<N>.json``; the current
    version is ``spec.json``) and ``amendment-v<N>.json`` for the receipt of the amendment
    that produced version N (``checkpoints/amendment-v<N>.json``).

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
    files = {f"protocol-v{version}.json": current}
    for n in range(1, version):
        data = _protocol_bytes(run_dir, f"spec_history/spec.v{n}.json")
        if data is not None:
            files[f"protocol-v{n}.json"] = data
    for n in range(2, version + 1):
        data = _protocol_bytes(run_dir, f"checkpoints/amendment-v{n}.json")
        if data is not None:
            files[f"amendment-v{n}.json"] = data
    return files


def protocol_digest(run_dir):
    """The run's protocol digest: the SHA-256 of the listing ``sha256sum`` prints for its
    protocol files under their names, names in byte order -- what
    ``cd 06_provenance/protocol/<id> && LC_ALL=C sha256sum $(LC_ALL=C ls) | sha256sum``
    prints for a run that ships its protocol. It changes at an amendment, never when a result
    is recorded."""
    files = protocol_files(run_dir)
    listing = "".join(
        f"{hashlib.sha256(files[name]).hexdigest()}  {name}\n" for name in sorted(files)
    )
    return hashlib.sha256(listing.encode("utf-8")).hexdigest()


def protocol_digest_cell(run_dir):
    """The run_index.csv cell: the protocol digest, or ``n/a`` when the files cannot be read."""
    try:
        return protocol_digest(run_dir)
    except (OSError, ValueError, AttributeError, TypeError):
        return "n/a"


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
                     "record_digest_sha256_12", "protocol_digest_sha256"])
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
            iw.writerow([rid, len(claims), verd, repro, dig, protocol_digest_cell(run_dir)])
            for c in claims:
                mode, ref = modes.get(c["hyp"], (c["mode"], ""))
                cw.writerow([rid, c["hyp"], mode or c["mode"], ref, c["status"],
                             c["point"], c["op"], c["threshold"], c["statement"]])
                n_claims += 1

    print(f"wrote {idx_path}: {len(runs)} runs")
    print(f"wrote {cl_path}: {n_claims} claims")


if __name__ == "__main__":
    main()
