"""
T-1 figures: a DETERMINISTIC RDKit molecule-structure plotter (the image source).

This resolves O-A of design/paper-figures-and-si.md for the molecular domain: the
render's IMAGE figure path (``render/figures.py:ImageFigureSpec`` ->
``\\includegraphics{figures/<id><ext>}``) needs a reproducible image *source*. Here it
is an RDKit 2D structure drawing produced FROM the record (a ``Molecule``), so a
molecular paper can carry a real structure figure that is part of the deterministic
record (re-render == byte-identical PNG, D2 -- verified against the real image).

Seam (design/rigor-shell-architecture.md §3.3, F4): this is DOMAIN-SPECIFIC (molecules)
so it lives in ``sci_adk.adapter``, NEVER the kernel. ``adapter -> kernel`` is allowed
and used: it imports the kernel figure TYPE ``ImageFigureSpec`` (from
``sci_adk.render.figures``) and the adapter ``Molecule`` (from
``sci_adk.adapter.t1_encoding``). The kernel never imports this module -- the CLI (the
composition root) does. The kernel stays free of RDKit and Docker entirely.

Execution seam (mirrors ``T1DockerExecutor`` in t1_capability.py EXACTLY): the plotting
is real RDKit, run inside the ``sci-adk-python-base`` container. A ``MoleculePlotter``
Protocol is the seam: the default ``RDKitDockerPlotter`` ships molecules as JSON to a
container script (``_PLOT_CONTAINER_SCRIPT``) that draws PNGs into the mounted
``/workspace`` and prints sentinel lines mapping each molecule to its written PNG path;
the plotter reads the bytes back. Tests inject an in-process fake. The DRAWING is never
faked -- only the container is a seam.

Determinism (D2, the headline): a pinned RDKit version (environments/python-base pins
``rdkit==2024.9.6``), a FIXED canvas size, ``Compute2DCoords`` (deterministic for a
pinned RDKit), and ``MolDraw2DCairo`` (cairo PNG carries NO timestamp metadata) make the
SAME molecule -> byte-identical PNG across runs. This was confirmed against the real
rebuilt image (two separate container runs, identical SHA256).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional, Protocol, Sequence

from sci_adk.adapter.t1_encoding import Molecule
from sci_adk.render.figures import ImageFigureSpec

# A fixed canvas size in pixels. Part of the determinism contract (D2): a constant
# width/height means a fixed-version RDKit emits byte-identical PNGs for a molecule.
# Square so portrait/landscape molecules render without canvas-driven layout drift.
_CANVAS_PX = 300

# A per-molecule sentinel the container script prints: ``<SENTINEL> <index> <png-path>``.
# The plotter parses these lines to recover which PNG belongs to which input molecule
# (mirrors how T1DockerExecutor parses the stats JSON off stdout -- the container speaks
# back over stdout, the host reads the files off the shared mount).
_PLOT_SENTINEL = "PLOT_OK"


class MoleculePlotter(Protocol):
    """The plotting seam ``build_molecule_figures`` depends on.

    ``plot_png(molecule) -> bytes`` returns the deterministic PNG bytes for the
    molecule's 2D structure. Production: ``RDKitDockerPlotter`` (real RDKit inside the
    container). Tests: an in-process fake returning placeholder PNG bytes. Either way the
    drawing is the seam's only stub -- the figure-building logic is exercised identically.
    """

    def plot_png(self, molecule: Molecule) -> bytes:
        ...


def hill_formula(molecule: Molecule) -> str:
    """Derive the Hill-notation molecular formula from a ``Molecule``'s atom multiset.

    Hill notation: Carbon first, Hydrogen second, then every other element
    alphabetically; a count of 1 is omitted (``H2O``, ``CO2``, ``CH4``). This is a
    record-derived, deterministic string -- the demo path uses it for an HONEST caption
    ("Structure of H2O") rather than an invented label. Pure (no RDKit needed): a figure
    caption must not depend on the container.

    Args:
        molecule: the explicit molecular graph (its ``atoms`` multiset is the input).

    Returns:
        The Hill-notation formula (empty string for an atom-less molecule).
    """
    counts: dict[str, int] = {}
    for symbol in molecule.atoms:
        counts[symbol] = counts.get(symbol, 0) + 1

    def _term(symbol: str) -> str:
        n = counts[symbol]
        return symbol if n == 1 else f"{symbol}{n}"

    ordered: List[str] = []
    if "C" in counts:
        ordered.append(_term("C"))
        if "H" in counts:
            ordered.append(_term("H"))
        for symbol in sorted(s for s in counts if s not in ("C", "H")):
            ordered.append(_term(symbol))
    else:
        # No carbon: pure alphabetical over every element (Hydrogen is not special).
        for symbol in sorted(counts):
            ordered.append(_term(symbol))
    return "".join(ordered)


def default_caption(molecule: Molecule) -> str:
    """A record-derived default caption for a molecule's structure figure.

    Uses :func:`hill_formula` so the caption is honest (the formula IS the record), not
    an invented description. Falls back to a generic phrase for an atom-less molecule.
    """
    formula = hill_formula(molecule)
    if not formula:
        return "Molecular structure"
    return f"Structure of {formula}"


def build_molecule_figures(
    molecules: Sequence[Molecule],
    captions: Optional[Sequence[Optional[str]]] = None,
    *,
    out_dir: Path,
    plotter: MoleculePlotter,
    ids: Optional[Sequence[str]] = None,
) -> List[ImageFigureSpec]:
    """Plot each molecule to ``out_dir/<id>.png`` and build matching ``ImageFigureSpec``s.

    For each molecule: get its deterministic PNG bytes from ``plotter`` (the seam), write
    ``out_dir/<id>.png``, and build an ``ImageFigureSpec(kind="image", id=<id>,
    caption=<caption>, image=<png path>)``. The kernel compiler later co-locates that PNG
    into ``paper/figures/<id>.png`` and the pure renderer emits the ``\\includegraphics``;
    here we only produce the source PNGs + specs (the adapter is a figure-source, not a
    filesystem owner of ``paper/``).

    Ids default to ``mol-0``, ``mol-1``, ... (LaTeX-safe slugs -> ``\\label{fig:<id>}``).
    Captions default to the record-derived Hill formula (:func:`default_caption`); a
    per-molecule ``None`` in ``captions`` also falls back to the default.

    Args:
        molecules: the molecules to draw (one figure each, in order).
        captions: optional per-molecule captions (parallel to ``molecules``); a missing
            or ``None`` entry -> the record-derived default caption.
        out_dir: directory the PNGs are written into (created if absent).
        plotter: the plotting seam (``RDKitDockerPlotter`` in production, a fake in tests).
        ids: optional explicit per-molecule ids (parallel to ``molecules``); default
            ``mol-<index>``. Each becomes the ``\\label{fig:<id>}`` AND the PNG stem.

    Returns:
        One ``ImageFigureSpec`` per molecule, in input order.

    Raises:
        ValueError: if ``captions``/``ids`` length mismatches ``molecules``, or if the
            resolved ids are not unique. A duplicate id would emit two
            ``\\label{fig:<id>}`` (a LaTeX "multiply defined label" error) and clobber one
            PNG with another -- so it fails loud rather than silently overwriting.
    """
    mols = list(molecules)
    if captions is not None and len(captions) != len(mols):
        raise ValueError(
            f"captions length ({len(captions)}) != molecules length ({len(mols)})"
        )
    if ids is not None and len(ids) != len(mols):
        raise ValueError(
            f"ids length ({len(ids)}) != molecules length ({len(mols)})"
        )

    resolved_ids = list(ids) if ids is not None else [f"mol-{i}" for i in range(len(mols))]
    seen: set[str] = set()
    for fig_id in resolved_ids:
        if fig_id in seen:
            raise ValueError(
                f"duplicate molecule figure id '{fig_id}' -- ids must be unique "
                r"(each becomes a \label{fig:<id>} and a PNG filename stem)"
            )
        seen.add(fig_id)

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    specs: List[ImageFigureSpec] = []
    for index, mol in enumerate(mols):
        fig_id = resolved_ids[index]
        caption = None
        if captions is not None:
            caption = captions[index]
        if not caption:
            caption = default_caption(mol)

        png_bytes = plotter.plot_png(mol)
        png_path = out_dir / f"{fig_id}.png"
        png_path.write_bytes(png_bytes)

        # ImageFigureSpec validates the id is a LaTeX-safe slug (the same check the
        # native path uses); ``image`` is the SOURCE path the compiler co-locates.
        specs.append(
            ImageFigureSpec(
                kind="image",
                id=fig_id,
                caption=caption,
                image=str(png_path),
            )
        )
    return specs


# ---------------------------------------------------------------------------
# RDKit Docker plotter (production path). Mirrors T1DockerExecutor: ships molecules as
# JSON, runs the real RDKit drawing inside sci-adk-python-base, reads PNGs back off the
# shared /workspace mount. Lazy imports so importing THIS module never needs Docker/RDKit.
# ---------------------------------------------------------------------------

class RDKitDockerPlotter:
    """Draw a molecule's 2D structure to a deterministic PNG via RDKit in the container.

    Mirrors ``T1DockerExecutor`` (t1_capability.py): the drawing is pure RDKit, run inside
    ``sci-adk-python-base`` (RDKit is NOT a host dependency, only a container one). It
    ships the molecule as JSON, the container script (:data:`_PLOT_CONTAINER_SCRIPT`)
    builds an RWMol from atoms+bonds, sanitizes, ``Compute2DCoords``, and draws via
    ``MolDraw2DCairo`` at the fixed :data:`_CANVAS_PX` size into a PNG on the shared
    ``/workspace`` mount, printing a ``PLOT_OK <index> <path>`` sentinel per molecule.

    Determinism (D2): the pinned RDKit version + fixed canvas + cairo's timestamp-free
    PNG make the SAME molecule -> byte-identical bytes (the load-bearing property; the
    integration test asserts it against the real image).
    """

    image_name = "sci-adk-python-base"

    def __init__(self, workspace_dir: Optional[Path] = None) -> None:
        # The shared mount: the container writes PNGs here, the host reads them back.
        # Defaults to cwd (the same default as T1DockerExecutor / DockerExecutor).
        self.workspace_dir = Path(workspace_dir) if workspace_dir else Path.cwd()

    def plot_png(self, molecule: Molecule) -> bytes:
        """Return the deterministic PNG bytes for ``molecule``'s 2D structure.

        Runs the container script over a single-molecule payload and reads the one PNG
        it wrote off the shared mount. Single-molecule by contract so the seam matches
        the ``MoleculePlotter`` Protocol (one molecule -> one PNG); ``build_molecule_
        figures`` calls it per molecule.

        Raises:
            RuntimeError: if the container run fails or writes no parseable PNG sentinel
                (e.g. the image lacks RDKit). The error names the stderr tail so a
                missing-RDKit image is diagnosable ("rebuild sci-adk-python-base with
                rdkit").
        """
        # Imported lazily so importing this module never requires Docker (mirrors
        # T1DockerExecutor's lazy import of DockerExecutor).
        from sci_adk.runner.docker_executor import DockerExecutor

        payload = json.dumps(
            [{"atoms": molecule.atoms, "bonds": [list(b) for b in molecule.bonds]}]
        )
        executor = DockerExecutor(
            image_name=self.image_name, workspace_dir=self.workspace_dir
        )
        run = executor.execute_python(
            _PLOT_CONTAINER_SCRIPT, script_args=[payload, str(_CANVAS_PX)]
        )

        paths = _parse_plot_sentinels(run.get("stdout") or "")
        if not run["success"] or 0 not in paths:
            raise RuntimeError(
                "RDKit plot container run produced no PNG (is rdkit installed in "
                f"'{self.image_name}'? rebuild sci-adk-python-base with rdkit). "
                f"stderr={(run.get('stderr') or '')[-400:]!r}"
            )
        png_rel = paths[0]
        png_path = self.workspace_dir / png_rel
        try:
            data = png_path.read_bytes()
        except OSError as e:  # noqa: PERF203 - one path, clear error
            raise RuntimeError(
                f"RDKit plot wrote sentinel '{png_rel}' but the PNG is unreadable: {e}"
            ) from e
        finally:
            # The PNG is a transient container artifact on the shared mount; the caller
            # (build_molecule_figures) persists the bytes to out_dir itself.
            if png_path.exists():
                png_path.unlink()
        return data


def _parse_plot_sentinels(stdout: str) -> dict[int, str]:
    """Parse ``PLOT_OK <index> <workspace-relative-png-path>`` lines into ``{index: path}``.

    Mirrors how T1DockerExecutor parses stats off the container's stdout: the container
    speaks the written PNG paths back over stdout (the bytes themselves stay on the shared
    mount). Lines without the sentinel prefix (RDKit warnings, etc.) are ignored.
    """
    out: dict[int, str] = {}
    for line in stdout.splitlines():
        parts = line.strip().split(" ", 2)
        if len(parts) == 3 and parts[0] == _PLOT_SENTINEL:
            try:
                out[int(parts[1])] = parts[2]
            except ValueError:
                continue
    return out


# The script executed inside the container. It reconstructs Molecules from the JSON
# payload, draws each via RDKit (deterministic: pinned version, fixed canvas, cairo PNG),
# writes ``_plot_<index>.png`` onto the shared /workspace mount, and prints a
# ``PLOT_OK <index> <path>`` sentinel per molecule. Mirrors _T1_CONTAINER_SCRIPT.
_PLOT_CONTAINER_SCRIPT = """
import sys, json
from rdkit import Chem
from rdkit.Chem import AllChem
from rdkit.Chem.Draw import rdMolDraw2D

payload = json.loads(sys.argv[1])
canvas = int(sys.argv[2])

_ORDER = {1: Chem.BondType.SINGLE, 2: Chem.BondType.DOUBLE, 3: Chem.BondType.TRIPLE}

def build(atoms, bonds):
    rw = Chem.RWMol()
    idx = [rw.AddAtom(Chem.Atom(sym)) for sym in atoms]
    for (i, j, order) in bonds:
        bt = _ORDER.get(order)
        if bt is None:
            raise ValueError("unsupported bond order %r" % (order,))
        rw.AddBond(idx[i], idx[j], bt)
    mol = rw.GetMol()
    Chem.SanitizeMol(mol)
    AllChem.Compute2DCoords(mol)
    return mol

for index, m in enumerate(payload):
    mol = build(m["atoms"], [tuple(b) for b in m["bonds"]])
    drawer = rdMolDraw2D.MolDraw2DCairo(canvas, canvas)
    drawer.DrawMolecule(mol)
    drawer.FinishDrawing()
    out_path = "_plot_%d.png" % index
    with open("/workspace/" + out_path, "wb") as fh:
        fh.write(drawer.GetDrawingText())
    print("PLOT_OK %d %s" % (index, out_path))
"""


__all__ = [
    "MoleculePlotter",
    "RDKitDockerPlotter",
    "build_molecule_figures",
    "hill_formula",
    "default_caption",
]
