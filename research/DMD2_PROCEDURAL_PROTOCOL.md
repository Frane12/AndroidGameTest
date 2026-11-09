# DMD2 Procedural Algebra Engine — experiment protocol (2026-11-09)

## Hypothesis
Formal algebra discovery becomes more useful when transformations are applied in
short certified *sequences*, and the next step prioritizes short consequences
and the measured increase in unit propagation. This is NOT a proven SAT speedup,
an undiscovered mathematical theorem, a new complete SAT solver, or P=NP.

## Implementation
- Reuse frozen native `research/dmd1_anf.cpp` as the low-level degree-2 ANF
  relation generator. The new `research/dmd2_procedural.py` is the **procedural
  controller**, not a new native CDCL implementation.
- Operate in at most three bounded stages. An optional algebra candidate comes
  from exhaustive local (up to eight variables) GF(2) monomial evaluation.
- Each stage can use certified previous lemmas as new premises. Reorder the
  *temporary analysis CNF* with newly proved clauses first; the final solver
  always gets the ORIGINAL CNF plus append-only proved lemmas.
- Independently replay every local implication by enumerating all satisfying
  assignments of its source bag, including previously proved stage lemmas.
- A second operator simplifies clauses under root units and **checks every
  proposed shortened clause by independent reverse unit propagation (RUP)**.
- Never trust relation length as a proof; only use it as a *heuristic* for
  ranking next actions. Retain several neutral algebraic discoveries to permit
  short delayed payoffs in the next stage.
- Canonicalize clauses, memoize lemma-set states, prohibit no-op cycles, and
  return to the unchanged solver when there are no useful/legal consequences.
- Track per-step: time, new verified clauses, root BCP units on a *subset view*
  (first 1200 original clauses plus derived facts), new BCP conflict flag,
  short clauses and feedback reward. The subset BCP comparison is a
  **heuristic signal only**, not a global solver progress metric.
- Charge C++ work, Python orchestration, local proof replay, DIMACS I/O,
  solver execution and original SAT witness validation to full E2E wall time.
  Limits 20 ms and 60 ms are SOFT internal budget targets; absolute limit
  is 6 s E2E. Run children sequentially, pinned to ONE logical CPU.

## Benchmark
Use 24 *previously tested* SHA-frozen original CNFs from EQUIV7 (first 24
by SHA), four previously used DMD1 SAT toys and four new synthetic chain
controls. Not a blind holdout. Randomized paired arm ordering, exact same
Kissat binary for five arms:
1. Original Kissat
2. DMD1 single-stage native ANF 15 ms active
3. DMD2 procedural <=3 stages, 20 ms active
4. DMD2 procedural <=3 stages, 60 ms SHADOW
5. DMD2 procedural <=3 stages, 60 ms active

32 cases x 2 repeats x 5 arms = **320** one-CPU E2E 6-second-cap trials,
four concurrent shards (one logical CPU *per independent trial*, not a
two-solver portfolio per formula).

## Mandatory audit
- Before benchmarks, compile native C++ with -Wall -Wextra -Werror, run
  DMD1's original 42 exhaustive tests and DMD2's 52 extra exhaustive tests.
- For each new derivation, independent local replay or RUP proof; for each
  original CNF, exact SHA verification; final output is append-only.
- All SAT witnesses validated against original source clauses; report UNSAT
  without independent LRAT and do not promote the build automatically.
- 320 unique paired source/rep/arm keys; per-shard and per-cohort PAR2, solved
  count, worst regression and best improvement; complete no-op/failure
  diagnostics rather than claiming a solved formula from bounded work.
- Positive outcome only if net E2E/PAR2 improves on ORIGINAL CNFs and
  shadow controls. A larger source-disjoint, pre-registered holdout is
  necessary before making claims of broad improvement.

## Reproducibility
```sh
mkdir -p mre_dmd2/bin
g++ -std=c++17 -O2 -Wall -Wextra -Werror research/dmd1_anf.cpp -o mre_dmd2/bin/dmd1_anf
python3 -u research/dmd1_bench.py selftest
python3 -u research/dmd2_bench.py selftest
# After restoring frozen EQUIV7 source CNFs and Kissat binary:
python3 -u research/dmd2_bench.py bench --shard 0
python3 -u research/dmd2_bench.py audit  # only when all shards are complete
```
