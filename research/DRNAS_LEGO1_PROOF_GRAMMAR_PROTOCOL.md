# DRNAS LEGO-1 — 5-second short E2E proof-carrying relation grammar

Separate experimental branch: experiment/drnas-lego1-proof-relation-grammar-20261109.
No changes to main, frozen baselines, or X24 branch.

## The idea

Like LEGO pieces, recurring simple relations can become new composable pieces:
- verified original-clause full XOR half-cubes (GF(2) rows, from native X24);
- verified signed binary implication *mutual paths* (not counts of edges);
- original unit clauses (exact parity facts).

Recursive XOR composition operates on GF(2) rows with the source-proof IDs
combined by symmetric difference. At EVERY candidate, Python replays the
complete original-clause source proofs and algebraic combination. Only implied
units, binary equivalences, inequivalences, and contradictions may be appended
as redundant clauses to the unchanged original CNF.

A table of fingerprints of join procedures ranks which already-proven
candidates to insert. The table is TRAINED ONLY on a disjoint set of original
SHA formulae using an explicit structural graph-reachability surrogate, not
SAT solving time, solver status, or outcomes. It never has authority to assert
truth or skip checking proofs. This does NOT constitute machine learning of a
general NP algorithm or real learned E2E benefit.

## Short, strictly paired experiment

Fixed X22 set of 24 original SHA formulae, sorted by SHA:
- First 8 train (no evaluation timings are used in training).
- Next 8 evaluate (two repetitions).
- Last 8 untouched reserved.
All 24 already appeared in X21/X22 and are NOT a fresh blind holdout.

Four strategies on each evaluation source/repetition:
1. original Kissat+CaDiCaL dual race;
2. unchanged X24 GF(2) proof-first;
3. LEGO static proof-grammar;
4. LEGO learned proof-grammar with frozen training-only relation table.

8 test sources x 2 seeds x 4 arms = 64 paired E2E trials.
4 concurrent shards x 16 attempts; 5 seconds wall cap PER attempt;
10-second PAR2 timeout penalty. CPU seconds, wall E2E, verified source SAT,
original UNSAT reference agreement (not LRAT), proof yield, added clauses,
fallbacks, learning statistics and preprocessing overhead are reported.

Native GF(2) extraction has a 0.65-second budget; whole LEGO preprocessing
has a 1.1-second budget, with fail-closed original-source race on timeout,
unsupported source or invalid proof. This fast pilot is meant to expose
useful/non-useful procedures and overhead, not certify generalization.
Future trials should use new genuine original-source SHA holdouts.

Important: the separate learned table is only a *structural proxy model*,
whose initial usefulness score is the number of new short binary implications
up to 3 hops. This proxy must not be confused with measured reduction
in CDCL conflicts or overall SAT execution time.

All SAT witnesses checked against the original CNF; UNSAT only original
Kissat+CaDiCaL cross agreement, no independent LRAT or FRAT evidence.
No auto-promotion.
