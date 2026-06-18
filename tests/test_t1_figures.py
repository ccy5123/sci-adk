"""
T-1 figures: the deterministic RDKit molecule plotter + figure-building (Phase 4-2).

Two layers, the same seam discipline as test_t1_adapter.py:
  - UNIT (no Docker): an in-process fake ``MoleculePlotter`` returns deterministic
    placeholder PNG bytes, exercising ``build_molecule_figures`` + the formula/caption
    helper. The figure-building logic is tested WITHOUT RDKit or a container.
  - INTEGRATION (gated): asserts ``RDKitDockerPlotter.plot_png`` returns valid PNG bytes
    AND that plotting the SAME molecule twice is BYTE-IDENTICAL (determinism / D2 -- the
    load-bearing assertion). Skipped if Docker is missing OR the image lacks rdkit.

The plotter is DOMAIN-SPECIFIC and lives in ``sci_adk.adapter`` (F4); it imports the
kernel ``ImageFigureSpec`` (adapter -> kernel, allowed). The kernel never imports it --
that one-way seam is already asserted by test_t1_adapter.py::TestSeamIsOneWay.
"""

from __future__ import annotations

import shutil
import subprocess

import pytest

from sci_adk.adapter.t1_capability import build_t1_demo_molecules
from sci_adk.adapter.t1_encoding import Molecule
from sci_adk.adapter.t1_figures import (
    RDKitDockerPlotter,
    build_molecule_figures,
    default_caption,
    hill_formula,
)
from sci_adk.render.figures import ImageFigureSpec

# A minimal but valid 1x1 PNG (the 8-byte signature + IHDR/IDAT/IEND). The fake plotter
# returns this so the unit tests assert real PNG bytes are written without needing RDKit.
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_FAKE_PNG = (
    _PNG_MAGIC
    + bytes.fromhex(
        "0000000d49484452000000010000000108060000001f15c4"
        "890000000a49444154789c6300010000050001"
        "0d0a2db40000000049454e44ae426082"
    )
)


class _FakePlotter:
    """A deterministic in-process ``MoleculePlotter`` (no RDKit, no Docker).

    Returns ``_FAKE_PNG`` for any molecule -- the figure-building seam only needs *some*
    bytes to write; the REAL drawing is exercised by the gated integration test. Records
    each call so a test can assert it was invoked once per molecule.
    """

    def __init__(self) -> None:
        self.calls: list[Molecule] = []

    def plot_png(self, molecule: Molecule) -> bytes:
        self.calls.append(molecule)
        return _FAKE_PNG


# ---------------------------------------------------------------------------
# Hill-formula / caption helper.
# ---------------------------------------------------------------------------

class TestHillFormula:
    @pytest.mark.parametrize(
        "atoms, expected",
        [
            (["O", "H", "H"], "H2O"),          # no carbon -> alphabetical (H before O)
            (["C", "O", "O"], "CO2"),          # carbon first, then O
            (["C", "H", "H", "H", "H"], "CH4"),  # C then H then rest
            (["C", "N", "H"], "CHN"),          # C, H, then N (alphabetical rest)
            (["C", "O", "H", "H"], "CH2O"),    # formaldehyde: C, H2, O
            (["O", "O", "H", "H"], "H2O2"),    # no carbon -> alphabetical H2 then O2
        ],
    )
    def test_hill_formula_known_molecules(self, atoms, expected):
        assert hill_formula(Molecule(atoms=atoms, bonds=[])) == expected

    def test_hill_formula_empty(self):
        assert hill_formula(Molecule(atoms=[], bonds=[])) == ""

    def test_default_caption_uses_formula(self):
        assert default_caption(Molecule(atoms=["O", "H", "H"], bonds=[])) == (
            "Structure of H2O"
        )

    def test_default_caption_empty_falls_back(self):
        assert default_caption(Molecule(atoms=[], bonds=[])) == "Molecular structure"


# ---------------------------------------------------------------------------
# build_molecule_figures (unit, fake plotter).
# ---------------------------------------------------------------------------

class TestBuildMoleculeFigures:
    def test_writes_png_files_and_returns_specs(self, tmp_path):
        mols = [
            Molecule(atoms=["O", "H", "H"], bonds=[(0, 1, 1), (0, 2, 1)]),
            Molecule(atoms=["C", "O", "O"], bonds=[(0, 1, 2), (0, 2, 2)]),
        ]
        plotter = _FakePlotter()
        out_dir = tmp_path / "figs"

        specs = build_molecule_figures(mols, out_dir=out_dir, plotter=plotter)

        # One spec per molecule, in order; the plotter was called once per molecule.
        assert len(specs) == 2
        assert len(plotter.calls) == 2
        for spec in specs:
            assert isinstance(spec, ImageFigureSpec)
            assert spec.kind == "image"

        # Default ids are mol-0, mol-1; default captions are record-derived Hill formulae.
        assert [s.id for s in specs] == ["mol-0", "mol-1"]
        assert specs[0].caption == "Structure of H2O"
        assert specs[1].caption == "Structure of CO2"

        # The PNG files were actually written, with valid PNG magic, at the spec paths.
        for spec in specs:
            png = out_dir / f"{spec.id}.png"
            assert png.is_file()
            assert png.read_bytes().startswith(_PNG_MAGIC)
            assert spec.image == str(png)

    def test_unique_ids_enforced(self, tmp_path):
        mols = [
            Molecule(atoms=["O", "H", "H"], bonds=[(0, 1, 1), (0, 2, 1)]),
            Molecule(atoms=["C", "O", "O"], bonds=[(0, 1, 2), (0, 2, 2)]),
        ]
        with pytest.raises(ValueError, match="duplicate molecule figure id"):
            build_molecule_figures(
                mols, out_dir=tmp_path, plotter=_FakePlotter(), ids=["dup", "dup"]
            )

    def test_custom_ids_and_captions(self, tmp_path):
        mols = [Molecule(atoms=["O", "H", "H"], bonds=[(0, 1, 1), (0, 2, 1)])]
        specs = build_molecule_figures(
            mols,
            captions=["Water molecule"],
            out_dir=tmp_path,
            plotter=_FakePlotter(),
            ids=["water"],
        )
        assert specs[0].id == "water"
        assert specs[0].caption == "Water molecule"
        assert (tmp_path / "water.png").is_file()

    def test_none_caption_falls_back_to_default(self, tmp_path):
        mols = [Molecule(atoms=["C", "H", "H", "H", "H"],
                         bonds=[(0, 1, 1), (0, 2, 1), (0, 3, 1), (0, 4, 1)])]
        specs = build_molecule_figures(
            mols, captions=[None], out_dir=tmp_path, plotter=_FakePlotter()
        )
        assert specs[0].caption == "Structure of CH4"

    def test_caption_length_mismatch_fails(self, tmp_path):
        mols = [Molecule(atoms=["O", "H", "H"], bonds=[(0, 1, 1), (0, 2, 1)])]
        with pytest.raises(ValueError, match="captions length"):
            build_molecule_figures(
                mols, captions=["a", "b"], out_dir=tmp_path, plotter=_FakePlotter()
            )

    def test_ids_length_mismatch_fails(self, tmp_path):
        mols = [Molecule(atoms=["O", "H", "H"], bonds=[(0, 1, 1), (0, 2, 1)])]
        with pytest.raises(ValueError, match="ids length"):
            build_molecule_figures(
                mols, out_dir=tmp_path, plotter=_FakePlotter(), ids=["a", "b"]
            )


# ---------------------------------------------------------------------------
# Integration: real RDKit in the container + determinism (D2). Gated on docker AND rdkit.
# ---------------------------------------------------------------------------

_IMAGE = "sci-adk-python-base"


def _docker_available() -> bool:
    return shutil.which("docker") is not None


def _rdkit_in_image() -> bool:
    """True iff the container image can import rdkit (probe -> skip with a clear reason).

    Runs ``python -c "import rdkit"`` inside the image. A non-zero exit means the image
    predates the rdkit activation, so the integration test skips with a rebuild hint
    rather than failing.
    """
    if not _docker_available():
        return False
    try:
        proc = subprocess.run(
            ["docker", "run", "--rm", _IMAGE, "python", "-c", "import rdkit"],
            capture_output=True,
            timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return proc.returncode == 0


rdkit_docker_required = pytest.mark.skipif(
    not _rdkit_in_image(),
    reason=(
        "docker + an rdkit-enabled sci-adk-python-base required; "
        "rebuild sci-adk-python-base with rdkit (environments/python-base)"
    ),
)


@rdkit_docker_required
class TestRDKitDockerPlotterIntegration:
    """The PRODUCTION drawing path: real RDKit inside sci-adk-python-base, and the
    headline determinism property (D2)."""

    def test_plot_png_returns_valid_png(self, tmp_path):
        plotter = RDKitDockerPlotter(workspace_dir=tmp_path)
        mol = Molecule(atoms=["O", "H", "H"], bonds=[(0, 1, 1), (0, 2, 1)])
        png = plotter.plot_png(mol)
        assert png.startswith(_PNG_MAGIC)
        assert len(png) > len(_PNG_MAGIC)

    def test_same_molecule_is_byte_identical(self, tmp_path):
        """D2: the SAME molecule -> byte-identical PNG across two independent container
        runs (pinned RDKit, fixed canvas, timestamp-free cairo PNG). This is the whole
        point of Phase 4-2 -- a figure is part of the deterministic record."""
        plotter = RDKitDockerPlotter(workspace_dir=tmp_path)
        mol = Molecule(atoms=["C", "H", "H", "H", "H"],
                       bonds=[(0, 1, 1), (0, 2, 1), (0, 3, 1), (0, 4, 1)])
        png_a = plotter.plot_png(mol)
        png_b = plotter.plot_png(mol)
        assert png_a == png_b
        assert png_a.startswith(_PNG_MAGIC)

    def test_build_molecule_figures_end_to_end(self, tmp_path):
        """The full demo path: real PNGs written for the T-1 demo molecules, with
        record-derived captions and unique ids."""
        mols = build_t1_demo_molecules()
        out_dir = tmp_path / "artifacts" / "figures"
        specs = build_molecule_figures(
            mols, out_dir=out_dir, plotter=RDKitDockerPlotter(workspace_dir=tmp_path)
        )
        assert len(specs) == len(mols)
        assert len({s.id for s in specs}) == len(specs)  # unique ids
        for spec in specs:
            png = out_dir / f"{spec.id}.png"
            assert png.read_bytes().startswith(_PNG_MAGIC)
            assert spec.caption.startswith("Structure of ")
