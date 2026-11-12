# DRNAS NATIVE X3 — Pattern / Step / Realized Progress

Independent C++20 SAT solver, built from DRNAS X2. X3 calls **no external solver**. All competition references live only in the Python benchmark.

## The three distinct signals
1. **Pattern** (structuralDistance): a fixed, evenly spaced sample of 96 *original* clauses, counting unsatisfied clauses that still have >2 unassigned literals. This is only a heuristic indicator.
2. **Step** (probe): bounded propagation for both polarities of three candidate variables. Compare structural change, conflicts and implications, then roll back the speculative trail. The probed decision is not considered a proof.
3. **Realized progress** (settleFeedback): after the chosen decision is *actually executed*, measure its realized implications, residual structure and whether BCP immediately caused a conflict. Aggregate feedback in windows of 8; disable probes temporarily when they rarely help or consume too much wall time. Also bypass probing in dense-conflict search regions.

## Modes
- `--mode core`: X3 C++ CDCL baseline with binary implication graph, watched literals, 1-UIP learning and restarts.
- `--mode gate`: CORE plus cheap structural prefilter followed by exact 2-SAT SCC only when possible; sound backdoor nogoods.
- `--mode x3` (default): GATE plus cost-aware, feedback-gated lookahead and polarity selection.

The cheap 2-SAT prefilter **never claims SAT/UNSAT**. If a sampled original clause is both unsatisfied and has 3+ unassigned literals, residual 2-SAT is impossible, so the expensive SCC scan is skipped. Otherwise complete original-CNF residual checking must still succeed before SCC solving.

A 2-SAT UNSAT leaf learns a nogood negating current decision assumptions, entailed by the original CNF. Never treat partial structural reduction as proof of SAT/UNSAT. A SAT candidate is verified on the *original* clauses internally and independently in benchmark.

## Build
```bash
mkdir -p build
g++ -std=c++20 -O3 -Wall -Wextra -Wpedantic -Werror src/drnas_x3.cpp -o build/drnas-x3
build/drnas-x3 input.cnf --mode core --time 5 --stats
build/drnas-x3 input.cnf --mode gate --time 5 --stats
build/drnas-x3 input.cnf --mode x3 --time 5 --stats
```
DIMACS exit codes: SAT=10, UNSAT=20, UNKNOWN=0, ERROR=1. JSON `X3_STATS` telemetry on stderr includes pattern samples, prefilter checks/rejects, exact 2-SAT SCC runs, actual feedback and cooldowns. Solver time cap begins **before DIMACS reading**; harness separately measures full process wall time. Parsing can slightly exceed the soft cap on huge inputs; benchmark penalizes end-to-end overruns.

## Validation and benchmark
```bash
g++ -std=c++20 -O3 src/drnas_x1.cpp -o build/drnas-x1
g++ -std=c++20 -O3 src/drnas_x2.cpp -o build/drnas-x2
python3 tests/test_x3.py --cases 2500
python3 research/drnas_x3_bench.py --smoke --synthetic-count 96 --smoke-cap .35
# references only in benchmark, with remotezip installed:
python3 research/drnas_x3_bench.py --official --official-cap 5
```
The tests compare all three X3 modes to an independent exhaustive truth-table oracle on small CNFs. The benchmark uses original SHA-disjoint sources, equal per-source caps, SAT witness verification, end-to-end PAR2 and per-family stats. X1, X2, Kissat, CaDiCaL and CryptoMiniSat are separate benchmark processes, never called by X3.

- Development smoke: deterministic synthetic formulas and previously used SAT2024 pool. **Not globally blind**; tuning on this set must be validated on a new source-disjoint holdout.
- For original SAT2024, UNSAT without external DRAT/LRAT certification remains **UNSAT_UNVERIFIED** and receives the PAR2 timeout penalty.
- Synthetic UNSAT construction checks are useful diagnostics, **not** general proof certificates.
- No claim of globally superior performance from one run or one sample.
- Future: independent UNSAT certificates, source-family-disjoint holdout, more adaptive resource allocation, optional GF(2) reasoning with proof checks.

This solver learns activity and uses short-lived feedback **within each solve**; it does not yet persist a trained model across runs.
