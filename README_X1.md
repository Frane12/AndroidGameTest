# DRNAS NATIVE X1 (prototype)

Independent native C++20 SAT solver. **No Kissat, CaDiCaL, CMS, Python, ML runtime,
or third-party SAT engine is linked or invoked by the X1 solving executable.**
Python is used only to prepare experiments and independently check SAT witnesses.

## Design: pattern vs distance to contradiction

- **Pattern**: immutable original-CNF hints (positive/negative literal balance,
  binary-clause density, occurrence count). Only biases the initial CDCL heap.
- **Step toward a problem**: dynamically observed implications/conflicts from
  temporarily assigning a candidate variable. `--mode horizon` briefly probes
  both polarities for the four highest-priority variables, rolls back the
  assignments, then branches. A short real conflict gets high priority.
- **Inference core**: original C++ watched literals, iterative unit propagation,
  decision trail, 1-UIP conflict analysis, learned clauses, VSIDS-like activity,
  phase saving, geometric restarts, activity-guided learned-clause reduction.
- **Proof policy**: original-CNF SAT witness verified inside X1 and again by
  benchmark harness. UNSAT results on large CNFs are *unverified* until DRAT/LRAT
  proof emission/checking is implemented. No claimed SAT speedup without a
  verified original-CNF witness, no claimed UNSAT speedup without verification.

This is a **research prototype**, not yet an optimized competitor to Kissat.
`horizon` is speculative and may be slower than `baseline`.

## Build and run

```bash
g++ -std=c++20 -O3 -Wall -Wextra -Wpedantic src/drnas_x1.cpp -o build/drnas-x1
build/drnas-x1 example.cnf --mode baseline --time 3 --stats
build/drnas-x1 example.cnf --mode horizon --time 3 --stats
```

Exit codes are 10 (SAT), 20 (UNSAT), 0 (UNKNOWN), 1 (input/internal error).
SAT writes a full DIMACS `v ... 0` witness. Telemetry is `X1_STATS` on stderr.

## Verification and benchmarks

```bash
python3 tests/test_random.py --cases 1400
python3 research/drnas_x1_bench.py --smoke
python3 research/drnas_x1_bench.py --official
```

The smoke suite has 100 distinct tiny CNFs (five families) and an independent
brute-force oracle, 2 modes x 100. These are **correctness/smoke tests**, not
credible evidence of speed superiority. The exploratory official benchmark
reuses a 12-source subset of the previously seen SAT2024 archive (4 small / 5
medium / 3 large): 2 DRNAS X1 modes against Kissat, CaDiCaL, CryptoMiniSat,
one logical CPU, equal 3 s cap, original SHA manifest and verified PAR2. It is
**not globally blind** and does not include a certified UNSAT check.

## Planned X2, conditional on X1 evidence

- Add proof trace / independent UNSAT certification (LRAT/DRAT) before any
  verified UNSAT leaderboard.
- Test implication-horizon score against graph/variable-pattern signals on
  *unseen*, source-family-disjoint CNFs; count probe overhead in wall time.
- Detect XOR gates and GF(2) equations with proof-preserving integration,
  not merely route to external CMS. Consider gate-level and circuit-native
  solving only when original structural provenance is available.
- Instrument graph cuts/backdoors and lookahead cost, separate static pattern
  from dynamic distance-to-conflict, and ablate each mechanism.
