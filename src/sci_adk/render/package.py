"""
The near-submission PACKAGE assembler (design/near-submission-package.md §1 / §C).

A package is the workspace-level SUBMISSION: ONE merged manuscript (``main.tex`` + ``si.tex``
+ figures) plus the standard 6-folder reproduction bundle, built from ALL the runs in the
workspace. This module is the deterministic spine that builds it -- it composes with the
per-run render layer (each ``runs/<id>/paper/`` stays the detailed internal record) rather
than replacing it.

[HARD] No LLM / no new belief (design §0): every number in the package is a recorded Claim
that reproduces under ``sci-adk verify``. The assembler INTERPRETS nothing; it co-locates the
per-run record outputs, runs the field-agnostic record-driven builders (the shipped
``04_scripts/*.py``), and -- when no author has supplied a merged ``main.tex`` -- emits a
DETERMINISTIC, tool-agnostic skeleton derived from the recorded hypothesis statements (the
authorial manuscript is the Wave-2 ``/sci package`` writer's job; the gate checks the
mechanically-checkable shape either way).

Deterministic + idempotent: re-running ``assemble_package`` over the same record produces the
same bytes (the record is frozen; the builders are deterministic; co-location is a copy). It
never writes outside ``<ws>/package/`` and never touches ``<ws>/pkgreqs.json`` (the frozen
contract lives at the workspace root, beside ``runs/``).

Layout (design §2 [2]):
  01_manuscript/   main.tex + si.tex + references.bib (+ figures/)
  02_data/         claims_all.csv (+ per-run claim CSVs)
  03_figures/      the figures + their per-run generators/specs
  04_scripts/      the field-agnostic builders + each run's official scripts
  05_inputs/       a copyright-respecting pointers README
  06_provenance/   run_index.csv + per-run verify logs
  MANIFEST.md      the file inventory
  README.md        overview + reproduction + submission-readiness self-assessment

Reference: design/near-submission-package.md, src/sci_adk/loop/compiler.py (the per-run
stage_render whose outputs are reused), src/sci_adk/templates/research-workspace/package/
04_scripts/ (the field-agnostic builders this invokes).
"""

from __future__ import annotations

import csv
import importlib.resources
import json
import math
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from sci_adk.core.pkgreqs import ALL_RUNS, PackageReqs
from sci_adk.core.spec import Spec
from sci_adk.loop.verify import verify_run
# The 6 canonical package folders are defined in the pure gate module (kernel-side, no
# verify_run dependency) so importing it here does not re-introduce a circular import; the
# assembler and the gate share that one source of truth.
from sci_adk.render.pkgreqs_checks import PACKAGE_FOLDERS

# The builders shipped under templates/research-workspace/package/04_scripts/. The assembler
# copies them into the package's 04_scripts/ (so the package is self-regenerating) AND runs
# them in-process to populate 02_data + 06_provenance + 01_manuscript/si.tex.
_BUILDER_NAMES: tuple[str, ...] = (
    "build_record_index.py",
    "make_si.py",
    "check_package.py",
)

# Reserved manuscript file the assembler emits when no author manuscript is supplied. An
# author-supplied main.tex (Wave 2 /sci package writer) is preserved -- the assembler never
# overwrites a hand-authored manuscript.
_MAIN_TEX = "main.tex"
_SI_TEX = "si.tex"
_REFERENCES_BIB = "references.bib"


@dataclass(frozen=True)
class PackageAssembly:
    """The result of assembling a workspace package (design §C).

    Attributes:
        package_dir: the assembled ``<ws>/package/`` directory.
        runs: the run ids synthesized (record order).
        folders_created: the 6 canonical folders laid down.
        main_tex_authored: True iff an author-supplied ``main.tex`` was preserved; False iff
            the deterministic record-derived skeleton was emitted (the Wave-2 writer replaces
            it). Surfaced so the caller can report that the manuscript is a skeleton.
        builder_outputs: file -> one-line note, the artifacts the builders produced
            (claims_all.csv, run_index.csv, si.tex).
        notes: free-form notes (e.g. a run with no per-run paper figures).
    """

    package_dir: Path
    runs: List[str]
    folders_created: List[str]
    main_tex_authored: bool
    builder_outputs: Dict[str, str] = field(default_factory=dict)
    notes: List[str] = field(default_factory=list)


def discover_runs(workspace_dir: Path) -> List[str]:
    """Every ``runs/<id>/`` holding a ``spec.json``, sorted by id (field-agnostic).

    PURE-ish (a directory listing). The selection sentinel ``"all"`` resolves to this; an
    explicit ``runs`` list in the contract is intersected with this so a stale id is dropped.
    """
    runs_root = workspace_dir / "runs"
    if not runs_root.is_dir():
        return []
    return sorted(
        d.name for d in runs_root.iterdir()
        if d.is_dir() and (d / "spec.json").is_file()
    )


def resolve_runs(workspace_dir: Path, pkgreqs: Optional[PackageReqs]) -> List[str]:
    """The runs the package synthesizes: the contract's selection ∩ the record (design §2).

    ``pkgreqs is None`` or ``runs == "all"`` -> every discovered run. An explicit list keeps
    only ids that actually exist on disk (record order), so a contract naming a removed run
    does not break assembly -- the gate's traceability check then reports any real gap.
    """
    discovered = discover_runs(workspace_dir)
    if pkgreqs is None or pkgreqs.runs == ALL_RUNS:
        return discovered
    wanted = set(pkgreqs.runs)
    return [rid for rid in discovered if rid in wanted]


def _builders_root() -> Path:
    """The shipped builders dir under the packaged research-workspace kit.

    Resolved via ``importlib.resources.files("sci_adk")`` (the same resolver
    ``init_session._templates_root`` uses), so it works for an editable install AND a built
    wheel. Raises a clear error if the builders are missing (a broken/partial install).
    """
    root = (
        Path(str(importlib.resources.files("sci_adk")))
        / "templates"
        / "research-workspace"
        / "package"
        / "04_scripts"
    )
    if not root.is_dir():
        raise FileNotFoundError(
            f"package builders not found at {root}; the sci-adk install appears "
            "incomplete (the packaged templates are missing). Reinstall sci-adk."
        )
    return root


def assemble_package(
    workspace_dir: Path,
    pkgreqs: Optional[PackageReqs] = None,
) -> PackageAssembly:
    """Assemble the 6-folder ``<ws>/package/`` from the workspace record (design §C).

    Deterministic + idempotent + no new belief. Steps:

      1. Resolve the runs (contract selection ∩ the record).
      2. Lay down the 6 canonical folders.
      3. Copy the field-agnostic builders into ``04_scripts/`` and co-locate each run's
         official scripts/figures (``runs/<id>/artifacts`` + ``runs/<id>/paper/figures``).
      4. Run the builders in-process to populate ``02_data/claims_all.csv``,
         ``06_provenance/run_index.csv``, and ``01_manuscript/si.tex`` from the frozen record.
      5. Co-locate the merged manuscript: preserve an author-supplied ``main.tex`` /
         ``references.bib`` if present; else emit a DETERMINISTIC, tool-agnostic skeleton from
         the recorded hypothesis statements (the authorial manuscript is the Wave-2 writer's
         job). Write per-run verify logs into ``06_provenance/``.
      6. Write ``MANIFEST.md`` + ``README.md`` (with the submission-readiness self-assessment).

    Args:
        workspace_dir: the workspace root holding ``runs/`` (and optionally ``pkgreqs.json``).
        pkgreqs: the frozen package contract, or None (then ``runs == "all"`` and the
            venue/format scaffolding is generic).

    Returns:
        A :class:`PackageAssembly` describing what was built.

    Raises:
        FileNotFoundError: if the shipped builders are missing (broken install).
        ValueError: if no runs with a ``spec.json`` are discoverable (nothing to package).
    """
    workspace_dir = Path(workspace_dir)
    runs = resolve_runs(workspace_dir, pkgreqs)
    if not runs:
        raise ValueError(
            f"no runs with a spec.json found under {workspace_dir / 'runs'} -- "
            "nothing to package (record is empty)"
        )

    package_dir = workspace_dir / "package"
    manuscript_dir = package_dir / "01_manuscript"
    for folder in PACKAGE_FOLDERS:
        (package_dir / folder).mkdir(parents=True, exist_ok=True)

    notes: List[str] = []

    # (3) Copy the builders + co-locate per-run scripts/figures/data.
    _copy_builders(package_dir)
    _colocate_run_artifacts(workspace_dir, package_dir, runs, notes)

    # (4) Run the builders in-process to populate the record-derived tables + the SI.
    builder_outputs = _run_builders(workspace_dir, package_dir)

    # (5) Merged manuscript: preserve an author-supplied main.tex/references.bib, else emit a
    # deterministic record-derived skeleton (tool-agnostic, names the science).
    main_tex_authored = _ensure_manuscript(workspace_dir, manuscript_dir, runs, pkgreqs)
    _write_verify_logs(workspace_dir, package_dir, runs)
    _write_inputs_readme(package_dir)

    # (6) The two index documents. The MANIFEST is written LAST among the folder-populating
    # steps so its inventory is complete + stable (every 05_inputs/06_provenance file already
    # exists); README.md is a ROOT file the inventory excludes, so its order does not matter.
    _write_manifest(package_dir, runs)
    _write_readme(package_dir, runs, pkgreqs, main_tex_authored)

    return PackageAssembly(
        package_dir=package_dir,
        runs=runs,
        folders_created=list(PACKAGE_FOLDERS),
        main_tex_authored=main_tex_authored,
        builder_outputs=builder_outputs,
        notes=notes,
    )


# -- (3) builders + per-run artifacts ----------------------------------------

def _copy_builders(package_dir: Path) -> None:
    """Copy the field-agnostic builders into ``04_scripts/`` (the package self-regenerates)."""
    builders_root = _builders_root()
    dest = package_dir / "04_scripts"
    for name in _BUILDER_NAMES:
        shutil.copyfile(builders_root / name, dest / name)


def _colocate_run_artifacts(
    workspace_dir: Path, package_dir: Path, runs: List[str], notes: List[str]
) -> None:
    """Co-locate each run's official scripts, figures, and per-run data into the package.

    Deterministic + idempotent (copy, overwriting prior copies). For each run:
      - ``runs/<id>/paper/figures/*`` -> ``03_figures/<id>/`` (the communication figures);
      - ``runs/<id>/artifacts/*``     -> ``04_scripts/runs/<id>/`` (the official analyses,
        whatever the experiment produced; field-agnostic -- no naming assumption).
    A run lacking a given source contributes nothing for it (recorded as a note), never an
    error -- a pointer-only / figure-less run is honest, not a failure.
    """
    figures_root = package_dir / "03_figures"
    scripts_root = package_dir / "04_scripts" / "runs"
    for rid in runs:
        run_dir = workspace_dir / "runs" / rid

        fig_src = run_dir / "paper" / "figures"
        if fig_src.is_dir():
            fig_dest = figures_root / rid
            _copytree_idempotent(fig_src, fig_dest)
        else:
            notes.append(f"run '{rid}': no per-run paper/figures/ to co-locate")

        art_src = run_dir / "artifacts"
        if art_src.is_dir():
            art_dest = scripts_root / rid
            _copytree_idempotent(art_src, art_dest)


def _copytree_idempotent(src: Path, dest: Path) -> None:
    """Copy ``src`` tree into ``dest``, overwriting (deterministic re-run)."""
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(src, dest)


# -- (4) run the record-driven builders --------------------------------------

def _run_builders(workspace_dir: Path, package_dir: Path) -> Dict[str, str]:
    """Run the builders IN-PROCESS to populate the record-derived tables + the SI.

    Imports the two generating builders as modules from the package's own ``04_scripts/`` (the
    copies just laid down) and calls their entry points with the workspace resolved -- no
    subprocess, deterministic. ``check_package.py`` is the reviewer self-check (run by the
    gate, not here). Returns file -> note for the produced artifacts.
    """
    import sys

    outputs: Dict[str, str] = {}
    scripts_dir = package_dir / "04_scripts"

    # build_record_index.py -> 06_provenance/run_index.csv + 02_data/claims_all.csv.
    _run_builder_module(
        scripts_dir / "build_record_index.py",
        "sci_adk_pkg_build_record_index",
        lambda mod: mod.main_with_args(str(workspace_dir), "package")
        if hasattr(mod, "main_with_args")
        else _invoke_index_builder(mod, workspace_dir, package_dir),
    )
    outputs["02_data/claims_all.csv"] = "per-Claim traceability (record-derived)"
    outputs["06_provenance/run_index.csv"] = "per-run verdicts + digest (record-derived)"

    # make_si.py -> 01_manuscript/si.tex.
    _run_builder_module(
        scripts_dir / "make_si.py",
        "sci_adk_pkg_make_si",
        lambda mod: mod.build(),
    )
    outputs["01_manuscript/si.tex"] = "Supporting Information record dump (record-derived)"

    # The dynamically-imported builder modules are throwaway; drop them so a re-run re-imports
    # fresh against the current package paths (the modules close over PKG/WS at import time).
    for name in ("sci_adk_pkg_build_record_index", "sci_adk_pkg_make_si"):
        sys.modules.pop(name, None)

    return outputs


def _run_builder_module(path: Path, mod_name: str, call) -> None:
    """Import ``path`` as ``mod_name`` and invoke ``call(mod)`` (a fresh import each call).

    Bytecode writing is suppressed for the import (``sys.dont_write_bytecode``) so the dynamic
    load does NOT drop a ``__pycache__/<mod>.pyc`` into the package's ``04_scripts/`` -- that
    cache would both pollute the shipped package and break the assembler's idempotence (its
    mtime/content shifts the MANIFEST on a rebuild). The flag is restored afterward.
    """
    import importlib.util
    import sys

    prev_dont_write = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec = importlib.util.spec_from_file_location(mod_name, path)
        if spec is None or spec.loader is None:
            raise FileNotFoundError(f"cannot load package builder: {path}")
        mod = importlib.util.module_from_spec(spec)
        sys.modules[mod_name] = mod
        spec.loader.exec_module(mod)
        call(mod)
    finally:
        sys.dont_write_bytecode = prev_dont_write


def _invoke_index_builder(mod, workspace_dir: Path, package_dir: Path) -> None:
    """Drive build_record_index's table writers against the resolved workspace.

    The builder's ``main`` parses argv; we call its pure pieces directly (discover_runs +
    load_claims + load_spec_modes + verify) so the assembler controls the workspace path
    without shelling out. Mirrors the builder's own ``main`` body, writing the same two CSVs.
    """
    import csv

    out = package_dir
    (out / "06_provenance").mkdir(parents=True, exist_ok=True)
    (out / "02_data").mkdir(parents=True, exist_ok=True)
    idx_path = out / "06_provenance" / "run_index.csv"
    cl_path = out / "02_data" / "claims_all.csv"

    runs = mod.discover_runs(str(workspace_dir))
    SY = {"supported": "S", "refuted": "R", "contested": "C", "proposed": "P"}
    with open(idx_path, "w", newline="") as fi, open(cl_path, "w", newline="") as fc:
        iw = csv.writer(fi)
        cw = csv.writer(fc)
        iw.writerow(["run_id", "n_hypotheses", "verdicts", "reproduced",
                     "record_digest_sha256_12"])
        cw.writerow(["run_id", "hyp_id", "mode", "referent", "status",
                     "point_statistic", "op", "threshold", "statement"])
        for run_dir in runs:
            import os

            rid = os.path.basename(run_dir)
            claims = mod.load_claims(run_dir)
            modes = mod.load_spec_modes(run_dir)
            repro, dig = mod.verify(run_dir)
            cnt: Dict[str, int] = {}
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


# -- (5) merged manuscript ---------------------------------------------------

def _ensure_manuscript(
    workspace_dir: Path,
    manuscript_dir: Path,
    runs: List[str],
    pkgreqs: Optional[PackageReqs],
) -> bool:
    """Preserve an author-supplied manuscript, else emit a deterministic skeleton.

    Source of an author manuscript: ``<ws>/package_src/{main.tex,references.bib}`` (the
    Wave-2 writer's drop point -- OUTSIDE ``package/`` so a rebuild does not erase it). When a
    ``main.tex`` is present there it is copied verbatim (author owns the prose); otherwise the
    assembler writes a record-derived, tool-agnostic skeleton naming the recorded hypotheses.
    A ``references.bib`` is copied from the author source if present, else a minimal empty bib
    is written so the manuscript's ``\\bibliography{references}`` resolves.

    Returns True iff an author ``main.tex`` was preserved.
    """
    author_src = workspace_dir / "package_src"
    author_main = author_src / _MAIN_TEX
    author_bib = author_src / _REFERENCES_BIB

    main_dest = manuscript_dir / _MAIN_TEX
    bib_dest = manuscript_dir / _REFERENCES_BIB

    if author_bib.is_file():
        shutil.copyfile(author_bib, bib_dest)
    elif not bib_dest.is_file():
        bib_dest.write_text(
            "% references.bib -- supply the manuscript's bibliography here.\n",
            encoding="utf-8",
        )

    if author_main.is_file():
        shutil.copyfile(author_main, main_dest)
        return True

    main_dest.write_text(
        _skeleton_main_tex(workspace_dir, manuscript_dir.parent, runs, pkgreqs),
        encoding="utf-8",
    )
    return False


def _skeleton_main_tex(
    workspace_dir: Path,
    package_dir: Path,
    runs: List[str],
    pkgreqs: Optional[PackageReqs],
) -> str:
    """A DETERMINISTIC, tool-agnostic merged ``main.tex`` derived from the record.

    No LLM, no new belief: the section scaffold is the declared/IMRaD required sections. The
    Results section is the P5 cross-run merge render (SPEC-PAPER-GATE-001 REQ-PG-501/502): it
    EXTRACTS each run's recorded quantities -- the per-Claim point statistic + pre-registered
    threshold -- from the package's own record table (``02_data/claims_all.csv``) and writes
    them as PLAIN numeric literals beside the verbatim recorded hypothesis statement, naming
    the science and no toolchain. Every other section is a prose slot the agent authors (the
    OD-7 boundary: numbers are record-extracted/gated, prose is free). The numbers it emits are
    record-backed BY CONSTRUCTION (the audit pool is built from that same CSV), so the
    manuscript passes P2 and a later hand-edit to any non-record value FAILS P2 (REQ-PG-503).
    The Wave-2 writer authors the prose slots; the package is gate-checkable throughout.
    """
    sections = (
        list(pkgreqs.required_sections)
        if pkgreqs and pkgreqs.required_sections
        else ["Abstract", "Introduction", "Methods", "Results", "Discussion", "Conclusion"]
    )
    ref_style = (pkgreqs.reference_style if pkgreqs else None) or "plainnat"

    lines: List[str] = []
    lines.append(r"\documentclass{article}")
    lines.append(r"\usepackage[margin=1in]{geometry}")
    lines.append(r"\usepackage{amsmath}")
    lines.append(r"\usepackage{newtxmath}")
    lines.append(r"\usepackage[scaled]{helvet}")
    lines.append(r"\usepackage{graphicx}")
    lines.append(r"\usepackage{natbib}")
    lines.append(r"\title{Near-submission package (skeleton)}")
    lines.append(r"\author{~}\date{}")
    lines.append(r"\begin{document}\maketitle")
    for name in sections:
        key = name.strip().lower()
        if key == "abstract":
            lines.append(r"\begin{abstract}")
            lines.append(
                "This manuscript synthesizes the pre-registered, independently reproduced "
                "results recorded across the project runs. It introduces no new experiment "
                "and no new claim; every quantitative statement is a recorded result that "
                "reproduces under a read-only audit (see the Supporting Information and the "
                "provenance index)."
            )
            lines.append(r"\end{abstract}")
            continue
        lines.append(r"\section{" + _tex_escape(name) + r"}")
        if key == "results":
            lines.append(_results_merge_render(workspace_dir, package_dir, runs))
        else:
            lines.append(
                "% (skeleton) author the " + _tex_escape(name) + " section to the package "
                "spec; the manuscript names the science, not the toolchain."
            )
    lines.append(r"\bibliographystyle{" + _tex_escape(ref_style) + r"}")
    lines.append(r"\bibliography{references}")
    lines.append(r"\end{document}")
    return "\n".join(lines) + "\n"


# A recorded comparison operator -> a neutral English phrase, so the merged manuscript renders
# the pre-registered criterion as the SCIENCE (a relation) without a math-mode literal (which
# the number-audit strips) and without a bare ``>``/``<`` that mis-renders in LaTeX text mode.
_OP_PHRASE: Dict[str, str] = {
    ">=": "at least",
    ">": "above",
    "<=": "at most",
    "<": "below",
    "==": "equal to",
    "=": "equal to",
    "!=": "not equal to",
}


def _results_merge_render(
    workspace_dir: Path, package_dir: Path, runs: List[str]
) -> str:
    """P5 cross-run merge render of the Results section (SPEC-PAPER-GATE-001 REQ-PG-501/502).

    EXTRACTS each recorded Claim's quantities -- the point statistic + the pre-registered
    threshold -- from the package's record table (``02_data/claims_all.csv``, the builder's
    deterministic dump) and writes them as PLAIN numeric literals beside the verbatim recorded
    hypothesis statement and outcome. Because the package number-audit pool
    (``RecordedValuePool.from_package``) is built from that SAME CSV, every literal emitted here
    is record-backed by construction: it passes P2 (REQ-PG-504), while a later hand-edit to any
    value the record does not hold FAILS P2 (REQ-PG-503). No value the record does not hold is
    introduced; the interpretation around the numbers is the agent's prose slot (OD-7 boundary).

    Falls back to the recorded hypothesis STATEMENTS alone (no value asserted) when the record
    table is absent -- the manuscript stays gate-checkable either way.
    """
    rows = _read_claims_rows(package_dir)
    out: List[str] = []
    if rows:
        for row in rows:
            out.append(_results_sentence(row))
    else:
        # Defensive fallback (record table not yet built): name the science, assert no value.
        for rid in runs:
            spec = _load_spec(workspace_dir / "runs" / rid)
            for hyp in spec.hypotheses:
                out.append(
                    "% " + _tex_escape(rid) + " / " + _tex_escape(hyp.id) + ": "
                    + _tex_escape(hyp.statement)
                )
    out.append(
        "Each recorded result above is established in the Supporting Information with its "
        "deterministic statistic and pre-registered acceptance criterion; the reproduction "
        "trail is in the provenance index."
    )
    return "\n".join(out)


def _read_claims_rows(package_dir: Path) -> List[Dict[str, str]]:
    """Every recorded-Claim row of ``02_data/claims_all.csv`` (the builder's record dump).

    READ-ONLY. Keys are the CSV header columns (``run_id``, ``hyp_id``, ``status``,
    ``point_statistic``, ``op``, ``threshold``, ``statement``, ...). A missing/unreadable table
    -> empty list (never raises), so the merge render falls back to the statement-only skeleton.
    """
    path = package_dir / "02_data" / "claims_all.csv"
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    return list(csv.DictReader(text.splitlines()))


def _results_sentence(row: Dict[str, str]) -> str:
    """One record-faithful Results sentence for a recorded Claim row (P5 extraction unit).

    The recorded point statistic + threshold are emitted as PLAIN numeric literals (audited
    against the package pool); the hypothesis statement + recorded outcome are verbatim science.
    A non-numeric cell simply contributes no literal -- never a fabricated value (REQ-PG-502).
    """
    rid = (row.get("run_id") or "").strip()
    hyp = (row.get("hyp_id") or "").strip()
    statement = (row.get("statement") or "").strip()
    status = (row.get("status") or "").strip()
    point = _csv_number(row.get("point_statistic"))
    threshold = _csv_number(row.get("threshold"))
    op_phrase = _OP_PHRASE.get((row.get("op") or "").strip())

    head = "For " + _tex_escape(rid) if rid else "The run"
    if hyp:
        head += " (" + _tex_escape(hyp) + ")"
    sentence = head + ", the pre-registered hypothesis"
    if statement:
        sentence += "---" + _tex_escape(statement) + "---"
    sentence += " was evaluated against its recorded statistic."
    if point is not None:
        sentence += " The recorded point statistic was " + point + "."
    if threshold is not None:
        crit = " The pre-registered threshold was " + threshold
        if op_phrase:
            crit += " (criterion: " + op_phrase + ")"
        sentence += crit + "."
    if status:
        sentence += " The recorded outcome was " + _tex_escape(status) + "."
    return sentence


def _csv_number(cell: Optional[str]) -> Optional[str]:
    """The cell's text iff it parses as a finite number (emittable as an audited literal), else
    None. The emitted text is the recorded cell VERBATIM -- the audit re-parses it to the same
    float the pool holds, so the literal is record-backed by construction."""
    text = (cell or "").strip()
    if not text:
        return None
    try:
        value = float(text)
    except ValueError:
        return None
    return text if math.isfinite(value) else None


def _load_spec(run_dir: Path) -> Spec:
    return Spec.model_validate(
        json.loads((run_dir / "spec.json").read_text(encoding="utf-8"))
    )


def _tex_escape(s: str) -> str:
    """Minimal LaTeX escaping for skeleton metadata (the record dump's esc, kept local)."""
    return (
        str(s)
        .replace("\\", r"\textbackslash{}")
        .replace("_", r"\_")
        .replace("%", r"\%")
        .replace("&", r"\&")
        .replace("#", r"\#")
        .replace("$", r"\$")
    )


def _write_verify_logs(workspace_dir: Path, package_dir: Path, runs: List[str]) -> None:
    """Write a per-run read-only audit log into ``06_provenance/verify_logs/`` (record audit).

    Deterministic: each log records the run's record digest + per-claim REPRODUCED/DIVERGED/
    UNRESOLVED + the overall reproduced flag -- the third-party-auditable companion to the
    run_index.csv. No re-run, no LLM (``verify_run`` is the headless audit).
    """
    logs_dir = package_dir / "06_provenance" / "verify_logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    for rid in runs:
        report = verify_run(workspace_dir / "runs" / rid)
        lines = [
            f"verified run '{report.spec_id}' -> runs/{rid}",
            f"  record digest (sha256): {report.digest}",
        ]
        for o in report.outcomes:
            rederived = (
                o.rederived_status.value if o.rederived_status is not None else "n/a"
            )
            lines.append(
                f"    - {o.hypothesis_id}: {o.result} "
                f"(recorded={o.recorded_status.value}, re-derived={rederived})"
            )
        lines.append(
            "  all recorded claims reproduced from the record"
            if report.all_reproduced
            else "  NOT reproduced: at least one claim DIVERGED or is UNRESOLVED"
        )
        (logs_dir / f"{rid}.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


# -- (6) MANIFEST + README ---------------------------------------------------

def _write_manifest(package_dir: Path, runs: List[str]) -> None:
    """Write ``MANIFEST.md`` -- the file inventory of the assembled package (deterministic)."""
    lines: List[str] = []
    lines.append("# MANIFEST -- near-submission package")
    lines.append("")
    lines.append(
        f"Assembled from the verify-green record at `runs/` ({len(runs)} run(s)). "
        "Every numerical statement in the manuscript is a recorded result that reproduces "
        "under the read-only record audit (`06_provenance/`)."
    )
    lines.append("")
    for folder in PACKAGE_FOLDERS:
        files = sorted(
            p.relative_to(package_dir).as_posix()
            for p in (package_dir / folder).rglob("*")
            # Skip Python bytecode caches: a stray __pycache__ must never enter the
            # deterministic inventory (the dynamic builder import suppresses writing them,
            # this is the belt-and-suspenders for any pre-existing cache).
            if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"
        )
        lines.append(f"## {folder}/ ({len(files)} file(s))")
        for rel in files:
            lines.append(f"- `{rel}`")
        lines.append("")
    lines.append("## Root")
    lines.append("- `README.md` -- overview, reproduction, submission-readiness self-assessment.")
    lines.append("- `MANIFEST.md` -- this file.")
    lines.append("")
    (package_dir / "MANIFEST.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_readme(
    package_dir: Path,
    runs: List[str],
    pkgreqs: Optional[PackageReqs],
    main_tex_authored: bool,
) -> None:
    """Write ``README.md`` with the REQUIRED submission-readiness section (design §C / §3)."""
    venue = (pkgreqs.venue if pkgreqs else None) or "(unspecified -- state the assumption)"
    lines: List[str] = []
    lines.append("# Near-submission package")
    lines.append("")
    lines.append(
        "A reproduction-study package compiled from the verify-green, pre-registered research "
        "record. It assembles the already-recorded, independently reproduced results of that "
        "record into one manuscript plus its full evidence trail. It introduces no new "
        "experiment and no new empirical claim: every number in the manuscript is a recorded "
        "result that reproduces under a read-only audit (`06_provenance/`)."
    )
    lines.append("")
    lines.append(f"- **Target venue:** {venue}")
    lines.append(f"- **Runs synthesized:** {len(runs)} ({', '.join(runs)})")
    lines.append("")
    lines.append("## Layout (standard reproduction-study)")
    lines.append("")
    lines.append("| folder | contents |")
    lines.append("|---|---|")
    lines.append("| `01_manuscript/` | `main.tex` + `si.tex` + `references.bib` (+ `figures/`) |")
    lines.append("| `02_data/` | `claims_all.csv` (master traceability) + per-run data |")
    lines.append("| `03_figures/` | per-run communication figures + generators |")
    lines.append("| `04_scripts/` | the field-agnostic package builders + each run's official scripts |")
    lines.append("| `05_inputs/` | copyright-respecting pointers to inputs |")
    lines.append("| `06_provenance/` | `run_index.csv`, per-run verify logs |")
    lines.append("")
    lines.append("## Reproduce")
    lines.append("")
    lines.append("From the parent workspace root:")
    lines.append("")
    lines.append("```")
    lines.append("for d in runs/*/; do sci-adk verify \"$d\"; done   # every run -> reproduced")
    lines.append("python3 package/04_scripts/build_record_index.py    # -> run_index.csv, claims_all.csv")
    lines.append("python3 package/04_scripts/make_si.py               # -> 01_manuscript/si.tex")
    lines.append("python3 package/04_scripts/check_package.py         # ref/label + cites + tool-vocab -> PASS")
    lines.append("```")
    lines.append("")
    lines.append("Then compile `01_manuscript/main.tex` and `si.tex` on any standard LaTeX install.")
    lines.append("")
    lines.append("## Traceability")
    lines.append("")
    lines.append(
        "Every number in `main.tex` and `si.tex` maps to a row of `02_data/claims_all.csv` "
        "via its run and hypothesis, and that row reproduces under `06_provenance/`. The "
        "manuscript interprets, frames, and discusses these recorded results (as any paper "
        "must) but asserts no value that is not one of them."
    )
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Submission-readiness self-assessment")
    lines.append("")
    lines.append(
        "**Filled within the record (done):** the package layout is complete; the manuscript "
        "and SI carry the deterministic record tables (`02_data/claims_all.csv`, "
        "`06_provenance/run_index.csv`); every quantitative statement traces to a reproduced "
        "Claim; author-facing prose names the science, not the toolchain; the full "
        "reproduction trail and digests are included."
    )
    lines.append("")
    lines.append("**Remaining gaps (record-external; cannot be closed from the frozen record):**")
    lines.append("")
    if not main_tex_authored:
        lines.append(
            "1. **Manuscript prose** -- `main.tex` is the deterministic record-derived "
            "skeleton. Author the Abstract / Introduction / Methods / Results / Discussion "
            "to the package spec (the `/sci package` writer)."
        )
    else:
        lines.append("1. **Manuscript prose** -- authored; review against the venue's author guidelines.")
    lines.append("2. **Author metadata** -- names, affiliations, ORCIDs, corresponding author.")
    lines.append("3. **Bibliography confirmation** -- confirm every cited reference (full citation + DOI).")
    lines.append("4. **Venue format compliance** -- conform headings, abstract length, and figure/table styling to the venue's author guidelines.")
    lines.append("5. **Final PDF pass** -- run a real `pdflatex` + `bibtex` pass (integrity here is structural).")
    lines.append("6. **Data/code availability** -- deposit the record (this package) to a public archive and cite its DOI.")
    lines.append("")
    lines.append(
        "Everything that can be completed from inside the record is complete; the remaining "
        "items are author decisions and external confirmations, not missing science."
    )
    lines.append("")
    (package_dir / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_inputs_readme(package_dir: Path) -> None:
    """Write the ``05_inputs/`` pointer README (copyright-respecting; nothing redistributed).

    Written BEFORE the MANIFEST (so the inventory is stable across rebuilds, design §C
    idempotence). Pointers only -- curated input values live in each run's official scripts.
    """
    (package_dir / "05_inputs" / "README.md").write_text(
        "# Inputs\n\n"
        "Pointers to the model inputs and any primary-literature sources used by the runs. "
        "Nothing copyrighted is redistributed here; curated values live in each run's "
        "official scripts (`04_scripts/runs/<id>/`).\n",
        encoding="utf-8",
    )


__all__ = [
    "PACKAGE_FOLDERS",
    "PackageAssembly",
    "assemble_package",
    "discover_runs",
    "resolve_runs",
]
