# An Injective Gödel-Style Encoding of Molecular Graphs: Empirical Verification on a Designed Test Set

> Draft authored by the in-session agent (sci-adk §4.4) over Spec `t1-godel` (v1).
> The belief stated here is **revisable**: it is the current Claim derived from the
> append-only Evidence, not a terminal result. Scope is stated honestly throughout.

## Abstract

We present a number-theoretic ("Gödel-style") encoding that maps a molecular graph to
a single recoverable integer, and we test its injectivity empirically. Each atom is
assigned an element prime; atoms are ordered by a Morgan-style canonical labeling
[1, 3]; the ordered elements and the bond structure are encoded as two prime-power
products `A` and `B`; and `A`, `B` are packed into one integer `G` via the Cantor
pairing bijection. On a designed test set of six small molecules the encoding produced
**zero collisions** and **exact round-trip recovery** (decode∘encode = identity),
which met a pre-registered decision rule and yielded a *supported* Claim. We are
explicit that this is empirical support for injectivity **on the tested sample** (an
exploratory claim), and **not** a proof of universal bijectivity: the canonical-labeling
step relies on iterative refinement, which is incomplete for graph isomorphism in
general [2].

## 1. Introduction

Serializing a molecular graph to a single integer is attractive for indexing,
deduplication, and number-theoretic manipulation. The classical route to a *unique*
machine description of a chemical structure is canonical labeling, introduced by Morgan
for Chemical Abstracts Service [1] and refined by a long line of cheminformatics work
on symmetry perception and rigorous canonicalization [3]. Separately, assigning primes
to symbols and exponentiating yields a Gödel numbering whose unique factorization makes
the code recoverable.

This work combines the two: a canonical labeling to make isomorphic graphs encode
identically, and a Gödel-style prime encoding to make the code injective and
invertible. The contribution is a concrete, runnable encoding plus an *exact verifier*
that measures injectivity (collision count) and recoverability (round-trip) on a
declared molecule set, evaluated against a frozen decision rule.

## 2. Method

**Encoding.** Elements are mapped to primes (H=2, C=3, O=5, N=7). Atoms are ordered by a
Morgan-style refinement — each atom's label is iteratively replaced by a signature over
its element prime and the multiset of its neighbors' labels and bond orders, to a
fixpoint, with a deterministic structural tie-break [1, 3]. With atoms in canonical
order `a_1..a_n` (element primes `e_i`), define `A = ∏_i P(i)^{e_i}` where `P(i)` is the
i-th prime; over canonical atom pairs `k` with bond order `b_k` (0 if unbonded),
`B = ∏_k P(k)^{b_k+1}`. Both are Gödel numbers: unique factorization recovers the element
sequence from `A` and the bond orders from `B`.

The two are packed into a single integer with the **Cantor pairing**
`G = (A+B)(A+B+1)/2 + B`, a bijection ℕ×ℕ→ℕ inverted exactly with integer square roots.
(We deliberately do *not* use the textbook `G = 2^A · 3^B`: with `A`≈10^7 for a
five-atom molecule, `2^A` is a multi-million-digit integer and cannot be materialized.
The Cantor pairing preserves injectivity and recoverability at feasible sizes — `G` for
CH₄ is 24 digits.)

**Verifier (exact, autonomous).** For a set of molecules we compute every `G`, report
`collision_count` (distinct molecules sharing a code) and `round_trip_ok`
(`encode(decode(G)) == G` for all), and emit these statistics. No threshold is hardcoded
in the verifier; the **decision rule is fixed in the Spec before results are seen**
(pre-registration): `collision_count == 0` ⇒ support (injective on the tested set);
`> 0` ⇒ refute. The decision engine applies this rule autonomously — no human or LLM
judgment is invoked for this numeric criterion.

## 3. Results

The test set was six small molecules with explicit graphs: H₂O, CO₂, CH₄, HCN, H₂O₂,
and formaldehyde (H₂C=O). The experiment, run in an isolated container, produced:

- `collision_count = 0` (every molecule received a distinct code),
- `round_trip_ok = true` (every code decoded back to its molecule),
- `n_molecules = 6`.

The pre-registered threshold rule was met, and the decision engine moved the hypothesis
`hyp-t1` to **supported**. Evidence: `evi-t1-20260616-111516-ddcad848` (kind:
`experiment_run`; statistic `collision_count = 0`). A complementary set constructed to
force a collision drives the same rule to *refuted*, confirming the rule discriminates.

## 4. Discussion and limitations

**Scope of the claim.** The supported Claim is **exploratory and sample-bounded**:
"molecule graphs admit an injective Gödel-style encoding *on the tested set*." It is
**not** a proof that the encoding is universally bijective. Zero collisions on six
molecules is evidence, not a theorem.

**The load-bearing limitation.** Injectivity hinges on the canonical labeling. The
Morgan-style refinement used here is *not* a complete graph canonicalization: refinement
alone cannot always distinguish highly symmetric or regular non-isomorphic graphs, for
which the general problem is graph-isomorphism-complete [2]. Two non-isomorphic molecules
that the refinement fails to separate would receive the same canonical order and could
collide *without being detected by the collision count*. Widening the molecule set beyond
this small sample therefore requires a complete canonical form (e.g., the
individualization-refinement approach of nauty/Traces [2]) before any broader injectivity
claim is warranted.

**Belief is revisable.** Consistent with sci-adk's record-vs-belief separation, this
Claim can be demoted or refuted by future Evidence (a discovered collision, a
counterexample, a failed reproduction) without contradicting the record. A universal
bijectivity statement would require a different, proof-type verification — out of scope
for this numeric cycle.

**Reporting note.** The decision engine's credence value for an exact-equality rule with
zero margin is uninformative (0.0); the binding outcome is the status (`supported`) and
its basis (the met `collision_count == 0` criterion), not that credence number.

## References

[1] H. L. Morgan. *The Generation of a Unique Machine Description for Chemical
Structures—A Technique Developed at Chemical Abstracts Service.* Journal of Chemical
Documentation 5(2):107–113, 1965. doi:10.1021/c160017a018.

[2] B. D. McKay and A. Piperno. *Practical Graph Isomorphism, II.* arXiv:1301.1493, 2013
(Journal of Symbolic Computation 60:94–112, 2014). doi:10.48550/arXiv.1301.1493.

[3] D. A. Krotko. *Atomic Ring Invariant and Modified CANON Extended Connectivity
Algorithm for Symmetry Perception in Molecular Graphs and Rigorous Canonicalization of
SMILES.* Journal of Cheminformatics 12, 2020. doi:10.1186/s13321-020-00453-4.

BibTeX: `runs/t1-godel/artifacts/literature/references.bib`. Open-access PDFs acquired
via paperforge for [2] (arXiv) and [3] (CC-BY); [1] has no open-access full text (cited
by DOI). Acquisition manifest: `runs/t1-godel/artifacts/literature/manifest.csv`.

---

Provenance: Spec `t1-godel` v1 · run `runs/t1-godel/` · capability `t1-molecular`
(container-executed) · Evidence `evi-t1-20260616-111516-ddcad848`. This paper is the
agent-authored artifact for sci-adk §4.4; wiring it into the deterministic renderer
(`render/paper.py`) so future compiles auto-assemble prose + references is a remaining
engineering step (architecture §4.5).
