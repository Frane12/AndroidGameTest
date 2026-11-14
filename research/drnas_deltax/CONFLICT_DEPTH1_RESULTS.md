# DELTAX conflict-depth 1 — synthetic discovery and debugging

Experiment: experiment/drnas-deltax-conflict-depth1-20261114
Successful GitHub Actions run: 43592275258
Source: 29 generated CNF formulas, 87 native solver runs; this is NOT 29 independent real-world families.

## Proof-first controls

- Three runs on every original CNF: JOIN, DELTAX-SHADOW, DELTAX active.
- All SAT assignments checked against exact source CNF, small truth-table oracle;
  every UNSAT certified on original source by independent DRAT check.
- Every emitted DELTAX guard clause is a checked one-step original resolution
  RUP consequence with an original binary reverse implication.
- 5 negative controls: 0 false alias candidates.
- 48 valid DELTAX-origin clauses installed in positive cases.
- 21 genuine live CDCL literal enqueues where the actual recorded reason is
  a DELTAX-origin clause. Shadow and JOIN causal counts: 0.

## Exact independent synchronous BCP-depth findings

A test harness does not control the native solver's branch order. It executes
plain synchronous Boolean unit propagation under explicitly disclosed
assignments, ONCE with only original clauses and ONCE with the DELTAX-resolved
one-step clause added. Do not conflate BCP waves with native CDCL decisions.

In all 24 positive generated instances:
  target propagation first appears at wave 2 with original source only,
  and wave 1 with independently proved short clause.
  A deliberately contradictory partial assignment produces a conflict
  at wave 1 with source only, versus wave 0 with the derived clause.

In all six selector-trap instances, a specified SELECTOR=TRUE branch
is unsatisfiable. The conflict wave is shortened by exactly one:
  selector_trap_0: wave 2 -> 1
  selector_trap_1: wave 3 -> 2
  selector_trap_2: wave 4 -> 3
  selector_trap_3: wave 5 -> 4
  selector_trap_4: wave 6 -> 5
  selector_trap_5: wave 7 -> 6

This is a shorter proof/propagation path, not a faster benchmark or a new
propositional implication beyond BCP closure.

## Important negative result

Compared with JOIN in the native CDCL solver:
  0 of 24 positive cases reduced the number of native decisions;
  0 of 24 positive cases reduced the number of native conflicts;
  0 cases increased either metric.
  The native solver recorded ZERO conflicts for all test cases in all arms.
  Thus NO earlier NATIVE CDCL conflict was demonstrated. Only the
  independently scripted partial-assignment BCP conflict depth improved.

Why this can happen: unit propagation already reaches a fixpoint before CDCL
makes the next decision; shaving one synchronous layer or substituting a
shorter RUP reason does not necessarily change the decision path. To prove
search benefit we need explicit condition-sensitive branch divergence or
a clause that changes the CDCL conflict graph on harder independent families.

## Scientific boundaries

All positive formulas share a known guarded-equivalence motif from the
real SAT2024 hardware-miter example, with varied tails, selector traps and
12 variable-renaming/reordering stimuli. This is useful reproducibility
and regression material, not evidence of general novelty or performance.

The synthetic source files, proof summaries, source hashes, paired native
trials and wave diagnostics are contained in artifact:
https://github.com/Frane12/AndroidGameTest/actions/runs/43592275258

No change to main or reference binaries, and no solver promotion.
