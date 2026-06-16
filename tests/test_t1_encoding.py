"""
T-1 real Gödel encoding of molecular graphs -- RED-first specification tests.

These pin the *science* of the encoding (NOT a toy): an explicit molecular graph
(atoms + bonds) is mapped to a single integer G via a number-theoretic, injective
scheme over a canonical labeling, and is recoverable (round-trip). The verifier
computes a ``collision_count`` over a designed test set -- the statistic the T-1
threshold DecisionRule judges autonomously.

Honest scoping (design/rigor-shell-architecture.md §4.2; abstractions C6): a zero
collision count over the *tested set* is empirical support for injectivity ON THAT
SAMPLE (an exploratory claim), never a universal proof of bijectivity. The tests
assert behavior on concrete designed molecules; they do not assert universality.

The encoding lives in the adapter layer (kernel stays domain-free,
design/rigor-shell-architecture.md §3.3 / F4) but is pure Python so it runs both
inside the Docker python-base image (production) and directly here (unit test)
without faking the science.
"""

from __future__ import annotations

import math

import pytest

from sci_adk.adapter.t1_encoding import (
    ELEMENT_PRIME,
    Molecule,
    decode_godel,
    encode_godel,
    nth_prime,
    verify_injectivity,
)

# ---------------------------------------------------------------------------
# Designed test molecules -- explicit graphs (atoms + bonds), not formula strings.
# Bonds are (i, j, order) with i < j, indices into the atoms list.
#   H2O: O bonded to two H (single bonds)        O-H, O-H
#   CO2: O=C=O (two double bonds)                 C=O, C=O
#   CH4: C bonded to four H (single bonds)        C-H x4
# ---------------------------------------------------------------------------

def _h2o() -> Molecule:
    # atoms: [O, H, H]; O(0)-H(1), O(0)-H(2)
    return Molecule(atoms=["O", "H", "H"], bonds=[(0, 1, 1), (0, 2, 1)])


def _co2() -> Molecule:
    # atoms: [C, O, O]; C(0)=O(1), C(0)=O(2)
    return Molecule(atoms=["C", "O", "O"], bonds=[(0, 1, 2), (0, 2, 2)])


def _ch4() -> Molecule:
    # atoms: [C, H, H, H, H]; C(0)-H(1..4)
    return Molecule(atoms=["C", "H", "H", "H", "H"],
                    bonds=[(0, 1, 1), (0, 2, 1), (0, 3, 1), (0, 4, 1)])


def _hcn() -> Molecule:
    # H-C#N : atoms [C, N, H]; C(0)#N(1) triple, C(0)-H(2) single
    return Molecule(atoms=["C", "N", "H"], bonds=[(0, 1, 3), (0, 2, 1)])


def _h2o2() -> Molecule:
    # hydrogen peroxide H-O-O-H: atoms [O, O, H, H]; O(0)-O(1), O(0)-H(2), O(1)-H(3)
    return Molecule(atoms=["O", "O", "H", "H"],
                    bonds=[(0, 1, 1), (0, 2, 1), (1, 3, 1)])


def _formaldehyde() -> Molecule:
    # H2C=O: atoms [C, O, H, H]; C(0)=O(1), C(0)-H(2), C(0)-H(3)
    return Molecule(atoms=["C", "O", "H", "H"],
                    bonds=[(0, 1, 2), (0, 2, 1), (0, 3, 1)])


# A pair the *toy* (atom-prime product, ignoring counts/bonds/structure) collides
# on but the real encoding must separate: CO2 (C,O,O / two C=O double bonds) vs a
# hypothetical isomer with the SAME atoms but single bonds. Same atom multiset,
# different bonds => different G.
def _co2_single_bonds() -> Molecule:
    # same atoms as CO2 [C,O,O] but single bonds (a distinct graph: O-C-O singly)
    return Molecule(atoms=["C", "O", "O"], bonds=[(0, 1, 1), (0, 2, 1)])


class TestNumberTheoryPrimitives:
    def test_nth_prime_sequence(self):
        # 1-indexed: P(1)=2, P(2)=3, P(3)=5, P(4)=7, P(5)=11, P(6)=13
        assert [nth_prime(i) for i in range(1, 7)] == [2, 3, 5, 7, 11, 13]

    def test_element_prime_map_covers_chno(self):
        assert ELEMENT_PRIME["H"] == 2
        assert ELEMENT_PRIME["C"] == 3
        assert ELEMENT_PRIME["O"] == 5
        assert ELEMENT_PRIME["N"] == 7


class TestEncodingInjectivity:
    """Distinct (non-isomorphic) graphs must encode to distinct integers."""

    def test_distinct_real_molecules_have_distinct_codes(self):
        mols = [_h2o(), _co2(), _ch4(), _hcn(), _h2o2(), _formaldehyde()]
        codes = [encode_godel(m) for m in mols]
        assert len(set(codes)) == len(codes), (
            f"collision among distinct molecules: {codes}"
        )

    def test_bond_order_changes_the_code(self):
        # CO2 (double bonds) vs same atoms with single bonds: the toy collides
        # (atom product identical); the real encoding must differ.
        assert encode_godel(_co2()) != encode_godel(_co2_single_bonds())

    def test_codes_are_positive_integers(self):
        for m in (_h2o(), _co2(), _ch4()):
            g = encode_godel(m)
            assert isinstance(g, int) and g > 0


class TestCanonicalLabeling:
    """Isomorphic graphs (same structure, atoms permuted) encode identically."""

    def test_atom_permutation_yields_same_code(self):
        # H2O written two ways: O first vs O last. Same graph, relabeled.
        a = Molecule(atoms=["O", "H", "H"], bonds=[(0, 1, 1), (0, 2, 1)])
        # Put O at index 2; H at 0 and 1. Same molecule, different vertex labels.
        b = Molecule(atoms=["H", "H", "O"], bonds=[(0, 2, 1), (1, 2, 1)])
        assert encode_godel(a) == encode_godel(b)

    def test_ch4_permutation_invariance(self):
        # C at index 0 vs C at index 4; the four H are interchangeable.
        # Bonds keep i < j (the Molecule invariant): H(0..3)-C(4).
        a = _ch4()
        b = Molecule(atoms=["H", "H", "H", "H", "C"],
                     bonds=[(0, 4, 1), (1, 4, 1), (2, 4, 1), (3, 4, 1)])
        assert encode_godel(a) == encode_godel(b)


class TestRoundTrip:
    """G decodes back to the canonical (atoms, bonds): injective by construction."""

    def test_round_trip_recovers_canonical_graph(self):
        for m in (_h2o(), _co2(), _ch4(), _hcn(), _formaldehyde()):
            g = encode_godel(m)
            recovered = decode_godel(g)
            # Re-encoding the recovered graph reproduces G (canonical fixpoint):
            assert encode_godel(recovered) == g
            # And the recovered atom multiset matches the input atom multiset.
            assert sorted(recovered.atoms) == sorted(m.atoms)

    def test_round_trip_preserves_bond_order_multiset(self):
        m = _co2()  # two double bonds
        recovered = decode_godel(encode_godel(m))
        in_orders = sorted(o for *_ , o in m.bonds)
        out_orders = sorted(o for *_, o in recovered.bonds)
        assert in_orders == out_orders


class TestVerifier:
    """The exact verifier emits the statistics the DecisionRule judges."""

    def test_clean_test_set_has_zero_collisions_and_round_trips(self):
        mols = [_h2o(), _co2(), _ch4(), _hcn(), _h2o2(), _formaldehyde()]
        stats = verify_injectivity(mols)
        assert stats["collision_count"] == 0
        assert stats["round_trip_ok"] is True
        assert stats["n_molecules"] == len(mols)

    def test_collision_count_detects_isomorphic_duplicates(self):
        # Feed two graphs that ARE isomorphic (same canonical form): the verifier
        # must count them as colliding (1 collision), since they share a G but are
        # presented as separate inputs. This proves the statistic is real.
        a = _h2o()
        b = Molecule(atoms=["H", "H", "O"], bonds=[(0, 2, 1), (1, 2, 1)])  # iso to a
        stats = verify_injectivity([a, b])
        assert stats["collision_count"] == 1

    def test_round_trip_ok_is_true_for_designed_set(self):
        stats = verify_injectivity([_co2(), _formaldehyde()])
        assert stats["round_trip_ok"] is True
