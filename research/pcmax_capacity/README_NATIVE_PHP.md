# DRNAS native source-clique / generalized pigeonhole prover (C++20)

Experimental proof-first specialist, **not** a general CDCL replacement.

## Overview

The standalone executable **drnas-php-native** reads untouched DIMACS CNF bytes,
extracts source-positive at-least-one demand clauses and source-negative binary
mutual-exclusion clauses, reconstructs a partition of resource cliques, and
checks every mutex edge against the original CNF.

When the number of disjoint demand groups exceeds the number of certified
resource cliques, the program emits a VeriPB 3.0 cutting-planes proof using
the original clause indices. The proof is created in the same native C++
process, published atomically without overwriting existing files, and
the program prints UNSAT with exit code 20. Unsupported or SAT inputs
return UNKNOWN (exit 0), without creating a proof. I/O errors exit 1.

**Critical distinction:** A native proof reported as
UNSAT_PBP_EMITTED_UNCHECKED is **not yet externally verified**. Standard
verification only counts after a separate pinned VeriPB checker accepts
the unchanged original CNF and its generated proof.

## Build

Requires C++20, CMake and OpenSSL Crypto development files.
The optional target is only available when OpenSSL is detected.
Existing main-branch CDCL targets were not changed.

~~~sh
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --target drnas-php-native -j2
~~~

## Run and verify

Use a new proof filename; existing proof files are never overwritten.

~~~sh
taskset -c YOUR_ALLOWED_CPU build/drnas-php-native ORIGINAL.cnf \
  --proof ORIGINAL.pbp --time 10
# When native exit code is 20:
veripb --cnf ORIGINAL.cnf ORIGINAL.pbp
~~~

The C++ executable itself uses no Python interpreter, CDCL backend, or
subprocess. The external VeriPB checker is deliberately separate.

## Six original SAT2026 test formulas

The frozen retrospective test contains six original SAT2026 exam-scheduling
CNFs from the previously source-pinned REAL2026-NEW16 benchmark.

All six new native C++ proofs passed independent pinned VeriPB 3.0.2 checks.
See the [GitHub Actions audit](https://github.com/Frane12/AndroidGameTest/actions/runs/43737095381)
and download the artifact named
**drnas-native-php6-original-veripb3-proofs-and-logs**.

Negative tests confirm a weakened satisfiable formula returns UNKNOWN,
a forged source/proof pair is rejected by VeriPB, and existing proof files
cannot be overwritten. One logical CPU per process is used in the test.

## Constraints and limits

This is not a blind, general SAT solver performance result. The native
structural fast path requires disjoint positive groups that cover declared
variables, each selected variable participating in exactly one source-proven
resource clique, and a strict capacity contradiction. Other CNFs return UNKNOWN.

Current bounds: at most 200,000 variables, 1,000,000 clauses, 30 MB original
input, 256 positive groups, and 100,000 proof steps. The format is VeriPB 3.0,
not DRAT/LRAT; competition acceptance depends on the event's proof rules.

Sources: [native C++](../../src/drnas_php_native.cpp) and
[reproduction harness](benchmark_native_php6.py).
