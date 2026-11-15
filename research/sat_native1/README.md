# DRNAS SAT-CONSTRUCT-NATIVE1: source-derived SAT witnesses

Experimental C++20 constructor and opt-in same-process X59 CDCL hook.
Main branch, historical tests, frozen solver references and APK are not changed.
No second solver, thread, or portfolio.

## Four constructive methods

- HORN: source-derived least model by unit forward chaining.
- 2SAT: implication graph with SCC assignment for binary source CNF.
- MATCH: source positive ALO groups, source binary mutex constraints,
  conservatively inferred resource components and bipartite matching.
- GF2: complete signed width-2/3/4 XOR patterns and source-backed
  exact-one parity rows; Gaussian elimination, then full-model verification.

EVERY candidate is checked against the full original CNF before SAT.
Unsupported structures, contradictions in partial analysis, expired budgets
and candidates failing verification return UNKNOWN, never inferred UNSAT.
These mathematical primitives are prior art. The new integration is an
experimental engineering combination, not a new complexity theorem.

The opt-in guard is --sat-construct-ms 25. Default is OFF. Supported
limits: 15,000 variables, 130,000 clauses, 600,000 literals; monotonic
clock budget. On UNKNOWN, unchanged original X59 CDCL continues.

## Compile

    mkdir -p build
    g++ -O3 -std=c++20 -DNDEBUG src/drnas_sat_construct.cpp -o build/drnas-sat-construct
    g++ -O3 -std=c++20 -DNDEBUG src/drnas_x59.cpp -o build/drnas-sat-native-x59
    build/drnas-sat-construct input.cnf --max-ms 25 --stats
    build/drnas-sat-native-x59 input.cnf --mode core --time 5 --sat-construct-ms 25 --stats
    python3 -u research/sat_native1/test_native.py

Standalone exit 10 is source-verified SAT with a full DIMACS v assignment;
exit 0 is UNKNOWN. The constructor never claims UNSAT nor exports UNSAT
DRAT/LRAT proofs.

## Deterministic controls

GitHub run:
https://github.com/Frane12/AndroidGameTest/actions/runs/43705908607

141 deterministic controls passed: Horn, 2-SAT, matching and XOR positive
cases; constructed UNSAT negatives; random planted SAT; and brute-force
negative controls. There were zero observed wrong SAT outcomes.
This is not a mathematical proof of implementation bug-freedom.

## Retrospective original SAT2024

The same run used the complete 100 previously exposed, frozen SAT2024
originals. Native alone at 150ms E2E cap: one verified SAT, 98 UNKNOWN,
one TIMEOUT. The one SAT is worker ID64 (MATCH).
SHA256: fc529dff1a6f763c97b0ed1dd33199e0d9dd26c50d210f9032e4fdaab5534c16

Five same-source paired repetitions on one logical CPU:

| Arm | Median verified E2E |
| --- | ---: |
| X59 OFF | 18.229 ms |
| X59 native ON | 15.962 ms |
| Standalone native constructor | 16.320 ms |
| Kissat | 52.062 ms |
| CaDiCaL | 88.263 ms |

With the native structural method enabled, median E2E was ~12.4% lower
than the same native X59 OFF (ratio ~1.14x). All five paired repetitions
were wins. This is one post-discovery source, not a general performance
result. The separate 20-original subset had no new verified SAT answers
for either X59 ON or OFF at 0.7s cap.

## Retrospective original SAT2026 exact XOR

GitHub run:
https://github.com/Frane12/AndroidGameTest/actions/runs/43706313821

Source GBD 75429ff7acb5acb597abe01aa745c2a6, SHA256
243e5d0079606862166a4619691cbbb8ffc9c8c14eb16250138b16d724c6bc83
with 250 variables and 1000 source clauses. One logical CPU; three
repetitions; original-CNF independent model checker.

| Arm | SAT verified | Median E2E |
| --- | ---: | ---: |
| Native C++ alone | 3/3 | 3.472 ms |
| Native X59 + GF2 | 3/3 | 3.597 ms |
| Pinned R28 GF2 | 3/3 | 3.120 ms |
| Native X59 OFF | 0/3 | timeout at 5s |
| Pinned Kissat | 0/3 | timeout at 5s |

Because Kissat timed out, the >1390x contrast is a CENSORED LOWER BOUND
for this one known XOR original, not an exact completed-run speedup.
R28 was slightly faster. GF(2) Gaussian elimination is established prior
art. The instance was previously examined; not blind, not a ranking.

## Scientific gate

Next: SHA-disjoint unseen official sources and mixed SAT/UNSAT controls;
independently verify all SAT witnesses and any UNSAT proof. Compare
verified end-to-end PAR2 to same-core Kissat, CaDiCaL and CryptoMiniSat,
including overhead, paired wins/losses and worst-case regressions.
Do not promote this module from these two selected examples.
