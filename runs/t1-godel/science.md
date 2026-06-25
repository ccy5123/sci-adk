# Spec-gate science findings (design/science-guards.md)

Structural weak-science patterns detected at spec-compile time (NEVER a halt). Resolve each by a Spec amendment (supply the missing artifact or a justification), then re-init/amend.

## G1 -- hyp-t1
- formal + deterministic (threshold) hypothesis asserting no novelty, still epistemic_kind='finding': a constructively-true / already-known result would be framed as an empirical discovery. Reclassify (epistemic_kind -> 'unit_test' if it is true by construction, 'capability_check' for a capability assertion) or assert novelty (novelty_result/novelty_method with a recorded found_nothing prior-art search). (G1)

## G2 -- hyp-t1
- formal + deterministic (threshold) hypothesis declares no discriminating_cases: a pass over an easy/undeclared test set is non-discriminating (a plausibly-broken method would pass it too). Declare the hard cases that make a pass informative, each with the reason it separates a correct method from a broken one. (G2)

## G3 -- hyp-t1
- formal + deterministic (threshold) hypothesis: a strict SUPPORTED will REQUIRE a NEGATIVE_CONTROL Evidence item -- a deliberately mutated method (broken so the hypothesis must be violated) that was actually run and on which the decision rule returned NOT-SUPPORTED, failing on the declared discriminating cases. Plan to record one (e.g. remove a tie-breaking invariant from the canonicalizer and confirm collisions appear). (G3)

## G4 -- hyp-t1
- mode-coherence: a frozen pre-registered threshold decision rule is treated as binding pass/fail, but mode=='exploratory' (where a rule is a guide, not a gate). Set mode='confirmatory' to honestly pre-register the hard threshold, or use a non-threshold rule for exploratory work. (G4)
