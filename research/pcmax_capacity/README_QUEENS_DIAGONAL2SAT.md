# DRNAS N-Queens — standard chess constraints and diagonal-driven 2SAT

This experiment is an independent, source-frozen synthetic CNF benchmark, **not** a blind SAT Competition result. The general DRNAS CDCL solver and `main` branch remain untouched.

## Two families, different complexity

**Standard N-Queens:** one queen in every row, at most one per column, at most one per diagonal. Cases n=2,3 (UNSAT by independent exhaustive oracle), n=8,16,32,64 (SAT with an independently checked explicit permutation). A source-variable permutation and clause permutation are applied before solver trials.

**Diagonal-only contradiction with domain restrictions (cycle2):** each of n queens can occupy only positions (row r, column r) or (row r, column r+1 mod n). A full matching exists if diagonal restrictions are removed, but adding both diagonal attack families makes the instance UNSAT. Cases n=32,128,512 with both diagonal-on UNSAT and diagonal-off SAT controls. Each generated formula is independently evaluated by an SCC 2SAT oracle; SAT controls also carry a full validated assignment. These are genuine row/column/diagonal attack rules but **not** unrestricted N-Queens.

## New proof-first module

`src/drnas_queens_2sat.cpp` is a standalone C++20 binary that accepts only original unit/binary CNF clauses and uses the implication-graph SCC algorithm (a well-known polynomial-time algorithm for 2-SAT). It produces a concise source-bound DRAT RUP certificate using two contradictory units and the empty clause. Its result **is not independently standard verified** until an external pinned drat-trim validates the unchanged original CNF plus proof file. For unsupported general formulas it returns UNKNOWN, not UNSAT.

The existing `drnas-php-native` is included as a separately measured baseline and uses VeriPB 3.0 for any positive source-clique proof. Kissat and CaDiCaL are also measured on the identical original CNF bytes; their raw status codes in this benchmark are not independently certified, and their SAT models are not parsed.

## Build and run

```bash
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --target drnas-queens-2sat drnas-php-native -j2
./build/drnas-queens-2sat original.cnf --proof brand-new.drat --time 12
# If exit code 20, independently verify:
./build/drat-trim original.cnf brand-new.drat
```

A fresh proof path is required. Inputs too large, clauses longer than 2, or instances with no detected contradiction return UNKNOWN without a proof; filesystem failures return error code 1. One logical CPU per process is used in GitHub Actions. Compare timing including external verification separately from detection time.

## Evidence

See [the paired benchmark run](https://github.com/Frane12/AndroidGameTest/actions/runs/43742144577) for frozen SHA-256 source manifests, proof logs, paired trials, and standard checker results. A successful synthetic 2SAT benchmark does not imply arbitrary N-Queens or general NP-complete SAT is polynomial-time solvable.
