# DRNAS native C++ structural to standard DRAT (BRIDGE8)

Status: GitHub Actions SUCCESS, run:
https://github.com/Frane12/AndroidGameTest/actions/runs/43730127360

This experiment does not modify main and is not an official blind SAT benchmark.

## Native implementation

* C++20 source: src/drnas_structural_drat.cpp.
* PCMAX Hall/PHP: validates source CNF ALO and AMO clauses before emitting extended-resolution DRAT.
* XOR/Tseitin: validates all CNF clauses for each recognized XOR row before bounded RUP elimination.
* Verifies the original DIMACS SHA-256 against the structural certificate.
* Runs independent drat-trim against the exact original CNF; no success without s VERIFIED.
* Fail closed on malformed source, unsupported certificate, resource limit, failed external checker, or tampered proof. Failed output proof is removed.
* Pinned to one Linux logical CPU. Python is used for benchmark orchestration only, not native proof generation.

Build on Ubuntu Linux:

    g++ -O3 -std=c++20 -DNDEBUG -Wall -Wextra -Wpedantic -pthread \
      src/drnas_structural_drat.cpp -lcrypto -o build/drnas-structural-drat

Run with source-bound structural certificate from DRNAS:

    build/drnas-unified-core1 original.cnf --time 5 --certificate cert.json
    build/drnas-structural-drat original.cnf cert.json out.drat \
      --checker build/drat-trim 5

For E2E benchmark, pass the *remaining* wall time, including proof checker.

## Results from paired GitHub CI

8 source-SHA-frozen previously exposed SYNTHETIC development CNFs,
3 repetitions, 3 arms, 72 trials total; one logical core, five-second
cap per trial and PAR2 timeout penalty of ten seconds.

| Arm | Accepted verified UNSAT | Strict PAR2 |
| --- | ---: | ---: |
| DRNAS + native C++ standard DRAT | 24/24 | 1.973473 s |
| Kissat | 21/24 | 33.084305 s |
| CaDiCaL | 21/24 | 33.895106 s |

Large aggregate gain is driven mainly by PHP 11 to 10:
native route median E2E 0.0893 s (3/3 verified),
Kissat and CaDiCaL 0/3 verified (timeouts).
On easy XOR/Tseitin, reference solvers can be faster.
This does NOT demonstrate general SAT speedup.

Five negative controls passed: wrong SHA, missing source Hall clause,
unavailable/failed external checker, incomplete DRAT, modified source CNF.

CI: .github/workflows/drnas-structural-drat-nativecpp.yml
Bench: research/structural_drat_bridge/native_test.py
Source generator: research/structural_drat_bridge/fixtures.py
Proof artifacts: GitHub run 43730127360

Next research milestone: a fresh, source-disjoint blind original-CNF
collection with standard proof verification, and only afterward consider
folding this companion C++ executable into the native solver binary.
