# DELTAX: synthetic proof and causal-CDCL experiment (14 Nov 2026)

Source branch: experiment/drnas-deltax-synthetic-causality-20261114
GitHub Actions run: https://github.com/Frane12/AndroidGameTest/actions/runs/43591183266

**Status: PASS.** This is a semantic-use experiment. No claimed runtime
speed improvement, generalization to unseen SAT formula families, or new
mathematical theorem. The seed structure was adapted from the REAL hardware
miter SAT2024 nonlinear separator, then reconstructed as small CNF formulas.
Eight cases are permutations of one structure, NOT independent discoveries.

## Protocol

- 17 separate synthetic CNFs; 12 positive guarded-equivalence constructions,
  5 negative controls (guard absent/partial, missing reverse clause, pure
  linear equivalence, and immediate UNSAT).
- Each formula tested in three modes with the SAME compiled diagnostic binary:
  JOIN, DELTAX-SHADOW, DELTAX active; 17 * 3 = 51 trials.
- SAT results checked against every original clause and small truth-table
  oracle. UNSAT results checked with independent original-CNF DRAT checker.
- Every emitted alias is checked against original parent clauses, its one-step
  resolution pivot, original reverse clause, and independent RUP.
- Separate instrumentation logs a causal event ONLY when the CDCL engine
  actually enqueues a literal using a DELTAX-origin clause as its REASON.
  It independently checks that every other literal in that reason is FALSE
  at that instant. Mere discovery or proof-logging is not counted.
- No source metadata is passed into the solver's recognition code. Positive
  inputs vary clause order, variable IDs, and unrelated constraints.

## Observed

- 24 proof-checked DELTAX-origin clauses installed on 12 positive cases.
- 10 actual CDCL enqueues whose immediate reason was a DELTAX-origin
  clause, occurring in 10 of the 12 positive cases.
- Exactly zero such enqueues in JOIN and SHADOW.
- Zero false guarded alias detections across all five negative controls.
- All 51 model/proof tests passed. One negative control is UNSAT, independently
  certified in each of its three modes.
- Aliases activate under their guard as expected. The positive fixtures
  use root-level guards, so a change in the guard during BACKTRACK was not
  established in this batch; the previous real-source experiment already
  separately demonstrated guard activation/deactivation accounting.

## Fully checked example

The positive guarded_core.cnf has 5 variables and 11 clauses. A is variable 1,
Z variable 2, guards are variables 3 and 4, and Y is variable 5.
Its two overlapping local relations together enforce A=Z=Y when guards
3 and 4 are FALSE. Both satisfying local states (A,Z,Y)=(0,0,0) and
(1,1,1) remain available.

Two ORIGINAL clauses:

    (-1 OR -2 OR 5)
    (-1 OR 2 OR 4)

resolve at variable 2 to give the absent-from-source, RUP-valid clause

    (-1 OR 4 OR 5).

At the partial assignment x3=0, x4=0, x1=1, synchronous unit propagation
using ORIGINAL CNF alone adds x2=1 in its first round, then x5=1 in
its second round. Adding the DELTAX-derived clause propagates x2=1 and
x5=1 in the FIRST round. This is a two-to-one reduction in *logical
propagation depth for this constructed assignment*, not 2x runtime speed.

The live CDCL log contains a causal event with implied literal 5 and
reason_clause [-1,4,5] at decision level 1. It is an actual propagation
reason, not an inferred counter.

Crucial limitation: ordinary BCP on the original formula eventually infers
x5 as well. DELTAX provides a shorter valid explanation / sooner local
propagation, NOT a new logical consequence beyond full BCP closure.
The meaningful next research question is whether such explanations can be
found usefully on diverse, SHA-disjoint real instances and whether they
reduce proof complexity or search effort.

## Reproduction

Download the original DELTA3 pinned source/binary preflight artifact from
run 43587320318. On this branch:

    python3 research/drnas_deltax/synthetic_causal_build.py
    python3 tests/test_drnas_deltax_synthetic.py

The GitHub Action handles artifact restoration, one logical CPU, model and
proof checkers, and saves the generated CNFs and per-case causal event logs.
No main changes or benchmark promotion.
