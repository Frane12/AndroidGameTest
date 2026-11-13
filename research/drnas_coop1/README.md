# DRNAS COOP1 — exact local Walsh / affine cooperation with CDCL

Experimental first build; no promotion. Base commit: d1e10d32e8fb82aab2c844b6a75f23383d640f95.
Frozen `src/drnas_x5.cpp` Git blob: 08ef5b13c0ab8c64bd93a4af3606cdc7d0b8e132.
The build script verifies this identity and generates a separate solver. Main,
frozen baselines, existing spectral experiments and training memory are untouched.

## Implemented mechanism

The solver receives only original DIMACS CNF. No generator labels, planted models,
expected statuses or variable categories enter the solver.

1. Select up to 64 local scopes, at most 8 variables and 256 original clauses each.
   Scopes include overlapping clause-support unions. All selected clauses are
   subsets of the original CNF; conclusions are globally valid when guarded.
2. At a CDCL propagation fixpoint, restrict each block to the current assignment.
   Enumerate at most 256 assignments and compute exact integer Walsh coefficients
   of the conjunction's indicator. This is NOT the sum-of-violations spectrum.
3. A coefficient with `abs(W(mask)) == feasible_count > 0` denotes a parity that
   holds for EVERY feasible local assignment. High-degree parity is retained in
   the analysis, not classified as GF(2) nonlinearity.
4. Emit only short consequences (one/two unassigned variables), plus the negated
   assigned block literals as guards. An infeasible block yields a guarded conflict.
   Before insertion, produce an explicit local resolution tree: each leaf weakens
   an original clause; each internal step is RUP. DRAT-Trim checks complete UNSAT
   proofs, and the small-instance tests independently check every proof prefix.
5. Unit/conflict clauses enter the existing reason graph and 1-UIP learning.
   Units are asserted at their highest antecedent level, ensuring persistence
   through backtracking, including unconditional root units.
6. Optional branching scores test how much fixing one variable reduces the affine
   hull defect `2^rank(points - point0) - number_of_points`. Defect zero means the
   feasible set is affine (or empty, separately handled). This does not equate
   Fourier degree with algebraic degree. Proposals alter only the next branch,
   never declare a result or prune an unproved branch.

This is exact LOCAL affine closure, not a global incremental Gaussian matrix,
not a complete ANF compiler and not a general SAT complexity improvement.
Spectrum and algebra run serially within the same CDCL process on one logical CPU.

## Controls and bounds

`--coop1 off`: unchanged baseline policy, no copying or analysis.
`--coop1 observe`: same local observations, no lemma insertion or branch changes.
`--coop1 algebra`: proof-producing short affine consequences, baseline branching.
`--coop1 on`: algebra plus affine-defect branching.

All benchmark modes use `--mode core --x5-no-minimize`. Independent X5_NO_MIN is
compiled from the frozen source and included alongside same-binary OFF.

Bounds: 4096 variables / 12000 stored original clauses, 64 windows, 24 passes,
8 lemmas/pass, 256 total lemmas, 8192 auxiliary proof steps. Window construction
checks a 10 ms deadline; passes check 2.5 ms deadlines, disabled once cumulative
analysis reaches 30 ms. These are cooperative bounds (individual bounded operations
can overshoot), not hard real-time guarantees. The external solve cap includes
parsing, analysis, proof production and solver process launch. Verification is
measured separately. The module never reads training or holdout memory.

## Validation and synthetic benchmark

Run:

```sh
mkdir -p build
# Build drat-trim.c from upstream commit 2e3b2dc0ecf938addbd779d42877b6ed69d9a985.
gcc -O2 build/drat-trim.c -o build/drat-trim
g++ -std=c++20 -O3 -DNDEBUG src/drnas_x5.cpp -o build/drnas-x5
python3 research/drnas_coop1/build.py
python3 tests/test_drnas_coop1.py
python3 research/drnas_coop1/benchmark.py --cap 1 --repeats 2
```

Safety: all 256 truth functions on 3 variables; 180 random CNFs up to 10 variables;
edge cases; targeted XOR cancellation and nonlinear examples. Four modes, independent
exhaustive oracle, original-CNF model validation, every proof step checked by a
separate Python RUP implementation, and independent DRAT-Trim UNSAT validation.
OBSERVE must preserve OFF search statistics and models. Invalid DIMACS and a fake
refutation must be rejected.

Benchmark: 42 unique CNFs, seven families, three sizes, two fixed disjoint generator
seeds per size. Two repetitions and five arms give 420 trials / 84 per arm. Arm
order is deterministically shuffled within each case/repetition; one CPU, serial.
Every formula has a frozen SHA-256. Seeds are separate from safety-test seeds,
but this is mechanism discovery, not a blind family-generalization study.

Families: sparse XOR SAT/UNSAT, repeated AND+XOR SAT/UNSAT, planted and unbiased
random 3-SAT, pigeonhole UNSAT. The AND+XOR UNSAT family deliberately contains a
contradictory local motif to test exact cooperation. Do not generalize an advantage
on this favorable construction to random XOR or real CNFs. Variable/sign and clause
permutations prevent position/metadata shortcuts.

Credited solves need an independent certificate AND total elapsed time within cap;
all others receive PAR2 = 2*cap. Invalid results fail the benchmark. Report regressions,
analysis overhead, proofs, conditioned windows, lemmas and actual branch changes.
Sub-millisecond effects are not evidence of reliable performance improvement.

The first smoke cohort solved all 420 attempts in milliseconds. A separately seeded
`--scale stress` cohort increases XOR/random3 sizes to 128/256/512 variables,
AND+XOR to 32/64/96 cells and pigeonhole to 8/9/10 pigeons. The solver is unchanged.
The GitHub workflow uses this larger cohort; both cohorts remain synthetic discovery.
