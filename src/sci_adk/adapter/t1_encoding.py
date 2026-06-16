"""
T-1: an injective Gödel-style encoding of molecular graphs (the real science).

A molecule is an explicit graph -- ``atoms`` (element symbols) + ``bonds``
(``(i, j, order)`` with ``i < j``, indices into ``atoms``). The encoding maps the
graph to a single integer ``G`` via number theory, over a *canonical labeling* so
that isomorphic graphs encode identically, and ``G`` is recoverable (round-trip).

Scheme (design/rigor-shell-architecture.md §4, "the encoding spec"):
    With atoms in canonical order a_1..a_n (element primes e_1..e_n):
        A = PROD_{i=1..n} P(i)^{e_i}                 # P(i) = i-th prime
    Over canonical atom pairs (i<j) in fixed order, with bond order b_k (0 if no
    bond between that pair):
        B = PROD_k P(k)^{b_k + 1}
    A is recoverable by factoring back into positional primes -> element exponents;
    B likewise -> bond orders. Both are Gödel numbers (injective by unique
    factorization), and both are SMALL integers (A,B for CH4 are 8 and 13 digits).

    PACKING A and B into one integer G -- DEVIATION FROM THE SPEC, FLAGGED HONESTLY:
    The architecture wrote ``G = 2^A * 3^B`` with ``A = v2(G)``, ``B = v3(G)``. That
    OUTER packing is computationally infeasible: A(CH4) ~= 1.07e7, so ``2^A`` alone
    is a ~3.2-MILLION-digit integer, and ``3^B`` is astronomically larger -- it
    cannot be materialized. The *inner* Gödel construction (A, B as prime-power
    products) is fine and is kept verbatim; only the doubly-exponential outer
    wrapper is replaced. We pack (A, B) with the **Cantor pairing function**
        G = (A+B)(A+B+1)//2 + B          # a bijection N x N -> N (number theory)
    inverted exactly with ``math.isqrt`` (A,B = cantor_inv(G)). Injectivity and
    round-trip are preserved identically -- distinct (atoms,bonds) -> distinct
    (A,B) -> distinct G -- at feasible integer sizes (G(CH4) is 24 digits). The
    spec's intent ("G is a single recoverable integer carrying A and B, injective
    within the canonical labeling") holds; only the carrier is feasible.

Honest scoping: perfect canonical labeling of graphs is GI-complete in general.
For the small T-1 test set, a Morgan-style iterative refinement plus a
deterministic tie-break is sufficient and is scoped as such -- this is empirical
support for injectivity ON THE TESTED SAMPLE (an exploratory claim), never a
universal proof of bijectivity.

This module is pure Python (no Docker, no third-party deps) so it runs unchanged
inside the ``sci-adk-python-base`` container (production) and directly in unit
tests (the science is never faked; only the container is a seam).

Two-environment note (design/tool-policy.md): this is sci-adk *product* runtime.
No success metric is hardcoded here -- the verifier merely emits statistics
(``collision_count``, ``round_trip_ok``); the DecisionRule (in the Spec) judges them.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

# Element -> prime. Extensible: add elements with the next unused small prime.
# These are the ELEMENT primes (the e_i exponents); the POSITIONAL primes P(i)
# used as bases are produced independently by ``nth_prime``.
ELEMENT_PRIME: Dict[str, int] = {"H": 2, "C": 3, "O": 5, "N": 7}

# Inverse map for decoding an element prime back to its symbol.
_PRIME_ELEMENT: Dict[int, str] = {p: e for e, p in ELEMENT_PRIME.items()}

Bond = Tuple[int, int, int]  # (i, j, order) with i < j


@dataclass(frozen=True)
class Molecule:
    """An explicit molecular graph: atoms + bonds.

    Attributes:
        atoms: element symbols, one per vertex (indexable 0..n-1).
        bonds: ``(i, j, order)`` triples, ``i < j`` indices into ``atoms``,
            ``order`` >= 1 (1 single, 2 double, 3 triple, ...).
    """

    atoms: List[str]
    bonds: List[Bond] = field(default_factory=list)

    def __post_init__(self) -> None:
        n = len(self.atoms)
        for a in self.atoms:
            if a not in ELEMENT_PRIME:
                raise ValueError(
                    f"unknown element {a!r}; extend ELEMENT_PRIME (known: "
                    f"{sorted(ELEMENT_PRIME)})"
                )
        for (i, j, order) in self.bonds:
            if not (0 <= i < n and 0 <= j < n):
                raise ValueError(f"bond index out of range: {(i, j, order)} (n={n})")
            if i >= j:
                raise ValueError(f"bond must have i < j (got {(i, j, order)})")
            if order < 1:
                raise ValueError(f"bond order must be >= 1 (got {order})")


# ---------------------------------------------------------------------------
# Number-theory primitives.
# ---------------------------------------------------------------------------

def _is_prime(num: int) -> bool:
    if num < 2:
        return False
    if num % 2 == 0:
        return num == 2
    d = 3
    while d * d <= num:
        if num % d == 0:
            return False
        d += 2
    return True


def nth_prime(n: int) -> int:
    """Return the n-th prime, 1-indexed: ``nth_prime(1) == 2``.

    A simple trial-division sieve-by-counting -- the T-1 graphs are tiny, so this
    is more than adequate and keeps the module dependency-free.
    """
    if n < 1:
        raise ValueError(f"nth_prime is 1-indexed; got {n}")
    count = 0
    candidate = 1
    while count < n:
        candidate += 1
        if _is_prime(candidate):
            count += 1
    return candidate


def _factor_exponents(value: int) -> Dict[int, int]:
    """Factor a positive integer into ``{prime: exponent}`` (trial division)."""
    if value < 1:
        raise ValueError(f"cannot factor non-positive integer {value}")
    exps: Dict[int, int] = {}
    remaining = value
    d = 2
    while d * d <= remaining:
        while remaining % d == 0:
            exps[d] = exps.get(d, 0) + 1
            remaining //= d
        d += 1 if d == 2 else 2
    if remaining > 1:
        exps[remaining] = exps.get(remaining, 0) + 1
    return exps


def _cantor_pair(a: int, b: int) -> int:
    """Cantor pairing: a bijection N x N -> N. ``pi(a,b) = (a+b)(a+b+1)/2 + b``.

    Replaces the infeasible ``2^a * 3^b`` packing (see module docstring) while
    keeping a single recoverable integer. Exact for arbitrarily large a, b.
    """
    if a < 0 or b < 0:
        raise ValueError(f"Cantor pairing needs non-negative ints, got ({a}, {b})")
    s = a + b
    return (s * (s + 1)) // 2 + b


def _cantor_unpair(z: int) -> Tuple[int, int]:
    """Invert ``_cantor_pair`` exactly using integer sqrt (no float precision loss)."""
    if z < 0:
        raise ValueError(f"cannot unpair negative integer {z}")
    w = (math.isqrt(8 * z + 1) - 1) // 2
    t = (w * (w + 1)) // 2
    b = z - t
    a = w - b
    return a, b


# ---------------------------------------------------------------------------
# Canonical labeling (Morgan-style refinement + deterministic tie-break).
# ---------------------------------------------------------------------------

def _adjacency(mol: Molecule) -> List[Dict[int, int]]:
    """Adjacency as a list of ``{neighbor_index: bond_order}`` per atom."""
    adj: List[Dict[int, int]] = [dict() for _ in mol.atoms]
    for (i, j, order) in mol.bonds:
        adj[i][j] = order
        adj[j][i] = order
    return adj


def _canonical_order(mol: Molecule) -> List[int]:
    """Return atom indices in a canonical order (isomorphism-invariant on the T-1 set).

    Morgan-style refinement: each atom starts with its element prime; each round
    its label becomes ``(own_label, sorted multiset of (neighbor_label, bond_order))``
    hashed to a small ordinal, iterated until the partition of labels stops
    refining. Atoms are then sorted by their final refined signature, with the full
    structural signature as a deterministic tie-break.
    """
    # @MX:WARN: [AUTO] this is NOT a complete graph-canonicalization -- it is a
    #   Morgan-style refinement + structural tie-break, sufficient ONLY for the small
    #   T-1 test set, and scoped as such (the resulting Claim is exploratory).
    # @MX:REASON: [AUTO] exact canonical labeling of arbitrary graphs is GI-complete;
    #   refinement alone can fail to distinguish regular/highly-symmetric graphs, which
    #   would let two non-isomorphic molecules share a canonical order (a false
    #   collision-free result). Widening the molecule set beyond the tested sample
    #   requires a real canonical-form algorithm before injectivity can be claimed.
    n = len(mol.atoms)
    if n == 0:
        return []
    adj = _adjacency(mol)
    elem_prime = [ELEMENT_PRIME[a] for a in mol.atoms]

    # Initial label: element prime (atoms of different elements never merge).
    labels = list(elem_prime)

    def refine_once(current: List[int]) -> List[int]:
        sigs = []
        for idx in range(n):
            neigh = sorted(
                (current[nb], order) for nb, order in adj[idx].items()
            )
            sigs.append((current[idx], tuple(neigh)))
        # Compress signatures to small ordinals, ordered deterministically.
        ordering = {sig: rank for rank, sig in enumerate(sorted(set(sigs)))}
        return [ordering[s] for s in sigs]

    # Iterate to a fixpoint of the partition (number of distinct labels stabilizes).
    prev_classes = -1
    for _ in range(n + 1):
        labels = refine_once(labels)
        classes = len(set(labels))
        if classes == prev_classes:
            break
        prev_classes = classes

    # Final structural signature per atom -- a stable, isomorphism-invariant key that
    # also encodes element + local environment for a deterministic tie-break.
    def structural_key(idx: int) -> tuple:
        neigh = sorted(
            (labels[nb], elem_prime[nb], order) for nb, order in adj[idx].items()
        )
        return (labels[idx], elem_prime[idx], len(adj[idx]), tuple(neigh))

    return sorted(range(n), key=structural_key)


def _canonical_pairs(order: List[int]) -> List[Tuple[int, int]]:
    """Canonical atom pairs (a<b in *canonical position* space), fixed order.

    Pairs are enumerated over canonical positions 0..n-1 as ``(p, q)`` with p<q,
    which is a fixed deterministic sequence given ``n``. The pair index k (1-based)
    selects the positional prime ``P(k)`` for the bond exponent.
    """
    n = len(order)
    return [(p, q) for p in range(n) for q in range(p + 1, n)]


# ---------------------------------------------------------------------------
# Encode / decode.
# ---------------------------------------------------------------------------

def _encode_A(mol: Molecule, order: List[int]) -> int:
    """A = PROD P(i)^{e_i} over canonical atom positions i=1..n (1-indexed P)."""
    elem_prime = [ELEMENT_PRIME[a] for a in mol.atoms]
    a_value = 1
    for pos, atom_idx in enumerate(order, start=1):
        a_value *= nth_prime(pos) ** elem_prime[atom_idx]
    return a_value


def _encode_B(mol: Molecule, order: List[int]) -> int:
    """B = PROD P(k)^{b_k + 1} over canonical atom pairs k=1.. (1-indexed P).

    The +1 exponent shift ensures every pair contributes (so the pair set is
    recoverable): a non-bonded pair contributes P(k)^1, a single bond P(k)^2, etc.
    """
    adj = _adjacency(mol)
    b_value = 1
    for k, (p, q) in enumerate(_canonical_pairs(order), start=1):
        atom_p, atom_q = order[p], order[q]
        order_pq = adj[atom_p].get(atom_q, 0)  # 0 if no bond
        b_value *= nth_prime(k) ** (order_pq + 1)
    return b_value


def encode_godel(mol: Molecule) -> int:
    """Encode a molecular graph to a single integer ``G = cantor_pair(A, B)``.

    A over canonical atom order, B over canonical atom pairs (see module docstring).
    Isomorphic graphs share a canonical order -> share ``(A, B)`` -> share ``G``
    (injective within the canonical labeling). The empty graph encodes A=B=1.
    """
    # @MX:ANCHOR: [AUTO] the injectivity contract -- distinct canonical graphs map to
    #   distinct G; isomorphic graphs map to the same G.
    # @MX:REASON: [AUTO] verify_injectivity, decode round-trip, the T-1 capability, and
    #   all encoding tests depend on this (atoms,bonds)->int mapping being injective
    #   within the canonical labeling; changing the scheme breaks every downstream code.
    order = _canonical_order(mol)
    a_value = _encode_A(mol, order)
    b_value = _encode_B(mol, order)
    return _cantor_pair(a_value, b_value)


def decode_godel(g: int) -> Molecule:
    """Recover a canonical ``Molecule`` from ``G`` (the round-trip / injectivity proof).

    ``(A, B) = cantor_unpair(G)``; factor A -> element-prime exponents per canonical
    position, B -> bond orders per canonical pair. The recovered molecule is in
    canonical labeling, so ``encode_godel(decode_godel(G)) == G``.
    """
    if g < 0:
        raise ValueError(f"G must be a non-negative integer, got {g}")
    a_value, b_value = _cantor_unpair(g)

    # A's factorization: positional prime P(i) ^ element_prime(position i).
    a_exps = _factor_exponents(a_value) if a_value > 1 else {}
    # Each present positional prime corresponds to exactly one atom; n = their count.
    n = len(a_exps)
    atoms: List[str] = [""] * n
    for i in range(1, n + 1):
        p_i = nth_prime(i)
        if p_i not in a_exps:
            raise ValueError(
                f"corrupt code: positional prime P({i})={p_i} missing from A={a_value}"
            )
        elem_prime = a_exps[p_i]
        if elem_prime not in _PRIME_ELEMENT:
            raise ValueError(f"corrupt code: unknown element prime {elem_prime}")
        atoms[i - 1] = _PRIME_ELEMENT[elem_prime]

    # B's factorization: pair prime P(k) ^ (bond_order + 1) over canonical pairs.
    b_exps = _factor_exponents(b_value) if b_value > 1 else {}
    pairs = _canonical_pairs(list(range(n)))
    bonds: List[Bond] = []
    for k, (p, q) in enumerate(pairs, start=1):
        p_k = nth_prime(k)
        exp = b_exps.get(p_k, 1)  # absent => exponent 1 => bond order 0 (no bond)
        bond_order = exp - 1
        if bond_order > 0:
            bonds.append((p, q, bond_order))

    return Molecule(atoms=atoms, bonds=bonds)


# ---------------------------------------------------------------------------
# Exact verifier -- emits the statistics the DecisionRule judges.
# ---------------------------------------------------------------------------

def verify_injectivity(molecules: List[Molecule]) -> Dict[str, object]:
    """Encode each molecule, count G-collisions, and check round-trip recovery.

    Returns a stats dict:
        - ``collision_count``: number of EXTRA molecules sharing a G with an earlier
          one (i.e. ``len(molecules) - len(distinct G values)``). Zero means every
          input got a distinct code (injective on this sample). Isomorphic inputs
          DO collide (they share a canonical form), so the count is honest.
        - ``round_trip_ok``: every G decodes back to a graph that re-encodes to the
          same G (injective by construction over the canonical labeling).
        - ``n_molecules``: the sample size.
        - ``codes``: the per-molecule integer codes (audit; may be large).

    No threshold is applied here (no hardcoded metric): the verifier only measures.
    The Spec's DecisionRule decides what ``collision_count`` means.
    """
    codes = [encode_godel(m) for m in molecules]
    distinct = len(set(codes))
    collision_count = len(codes) - distinct

    round_trip_ok = True
    for m, g in zip(molecules, codes):
        if encode_godel(decode_godel(g)) != g:
            round_trip_ok = False
            break

    return {
        "collision_count": collision_count,
        "round_trip_ok": round_trip_ok,
        "n_molecules": len(molecules),
        "codes": [str(c) for c in codes],  # str: codes can exceed JSON int range
    }


__all__ = [
    "ELEMENT_PRIME",
    "Molecule",
    "nth_prime",
    "encode_godel",
    "decode_godel",
    "verify_injectivity",
]
