# Demonstrate an injective Gödel-style encoding of molecular graphs on a designed test set (unique integer per non-isomorphic molecule).

> Draft compiled by sci-adk from Spec `t1-godel` (v1). Belief state is revisable as Evidence accrues.

## Goal
Demonstrate an injective Gödel-style encoding of molecular graphs on a designed test set (unique integer per non-isomorphic molecule).

## Background
Molecular graphs can be serialized to integers. A Gödel-style prime encoding promises an injective, recoverable mapping.

## Method
Canonically label each graph (Morgan-style refinement), encode atoms and bonds as prime-power products packed into one integer, and verify zero collisions plus exact round-trip decode over the test set.

Planned approaches:
- prime-Gödel graph encoding

## Hypotheses and findings

### Molecule graphs admit an injective Gödel-style encoding on the tested set
- Hypothesis id: `hyp-t1` (exploratory)
- Decision rule (threshold): collision_count == 0 over the test set => support (injective on the tested set); collision_count > 0 => refute
- **Status: supported** — confidence 0 (credence)
- Basis: threshold rule: statistic 'point'=0 == 0 is met (combine='latest', margin=0)

## Evidence
- `evi-t1-20260616-111516-ddcad848` (experiment_run): point=0, finding={"statistic": "collision_count", "collision_count": 0, "round_trip_ok": true, "n_molecules": 6, "capability": "t1-molecu
