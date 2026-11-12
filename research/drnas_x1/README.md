# DRNAS X1 — native C++20 research solver

A new, independently implemented solver for Frane Drnas / DRNAS. No Kissat,
CryptoMiniSat, CaDiCaL, MiniSat, external solver library, subprocess or remote
service is used by the X1 executable. The benchmark launches competitors only
as separate measured arms. Standard-library/runtime dependencies are not SAT
backends. This is a research prototype, not a claim of a new complexity result
or a competition-winning solver.

## Implemented now

* **CORE:** strict DIMACS parser, two watched literals with blocking literals,
  indexed activity heap, saved phases, first-UIP conflict learning, nonchronological
  backjumping, geometric restarts, locked-clause-aware learned clause reduction,
  and a DRUP proof stream. SAT witnesses are checked against original clauses.
* **FACTOR:** an alternative, non-CDCL exact solver. Clauses become small tables
  of permitted assignments; all factors mentioning a selected variable are joined
  and that variable is existentially eliminated. Witness tables reconstruct SAT
  assignments backwards. UNSAT produces an elimination-order certificate.
  Tables are packed in 64-bit words; this first version still evaluates joins
  assignment-by-assignment, not SIMD vectorized.
* **AUTO:** tries bounded exact factor elimination, then uses our own CORE on the
  ORIGINAL formula when the factor route abstains. No competing solver is called.
  Partial factor progress is deliberately not imported into CORE in X1 v1.
* **Independent checks:** a separate Python parser/model checker; a simple,
  scan-based DRUP checker; and an elimination checker implemented with explicit
  boolean-tuple relations instead of the solver's bitsets. CI additionally checks
  CORE/competitor UNSAT proofs using separately built, pinned DRAT-trim.

These algorithms are established techniques, not asserted to be inventions.
The original implementation and the bounded dual-representation experiment are
what this X1 branch contributes to the DRNAS project.

## Build and use

```sh
g++ -std=c++20 -O3 -DNDEBUG research/drnas_x1/x1.cpp -o drnas-x1
./drnas-x1 --mode auto --seconds 3 --proof answer.proof problem.cnf > answer.txt
# SAT exit code 10; UNSAT 20; UNKNOWN/budget exhaustion 0; invalid input 1.
python3 -S research/drnas_x1/check.py problem.cnf answer.txt --proof answer.proof
python3 -S research/drnas_x1/test.py ./drnas-x1 --cases 2000 --report tests.json
```

`--mode core|factor|auto`; `--width 4..16` defaults to 12; `--seed 17` controls
CORE tie breaking. FACTOR-only returns UNKNOWN on a width/resource limit.

## Bounds and correctness

AUTO's factor attempt has a 50 ms / 3% nominal time budget (whichever is smaller),
2 million factor-lookup budget and a maximum union scope of 12 variables by
 default. There are eligibility guards of 2,048 declared variables and 20,000
normalized clauses; longer clauses than the width cap cause abstention. Budget
checks are periodic, so the benchmark also applies a hard external wall-time
limit. These are conservative INITIAL settings, not tuned winners. A 12-variable
factor has at most 4,096 assignments. Global SAT remains potentially exponential;
large induced width can make this method inappropriate.

The source CNF is never overwritten. Table elimination is exact existential
quantification, not an approximate guess. For SAT, reconstructed assignments
must satisfy every original clause. For UNSAT, an unverified claim earns no
verified benchmark credit. Custom FACTOR replay is not DRAT/LRAT and its checker
has not been formally verified. Tests are evidence, not a proof that all solver
implementations are bug-free.

Both proof writers and benchmark subprocesses have an 8 MiB proof/file cap.
Temporary proofs and original downloaded CNFs are NOT uploaded as artifacts.
Reaching a resource or validation limit is reported, not converted into UNSAT.

## Benchmark protocol

`bench.py --suite official100` reuses **only source acquisition** from
`drnas_ltm11_real2.py` in the frozen parent branch. It does not call that module's
solver routines. Select 100 original SAT2024 CNFs without solver outcome labels,
one per normalized filename family, sort by variables/bytes/SHA and allocate
50 cases 3 seconds and 50 cases 5 seconds. These are time limits, not a promise
that those formulas solve within those limits. This archive has been seen in
previous DRNAS runs: **exploratory, not globally blind**.

Four serial arms: X1_CORE, X1_AUTO, Kissat and CaDiCaL, one logical CPU, rotating
order, one repetition, proof generation enabled for every arm. CMS is not in
this initial proof-certified comparison: the Ubuntu CMS package emits FRAT,
which needs a different proof pipeline. We do not penalize an unsupported proof
format as a solver failure or silently disable certification to include it.

Report source hashes, formula family, status, decisions/conflicts, factor route,
proof size, solve time, independent check time and regressions. Primary
`PAR2_verified_e2e_s` counts solve + check if certified within the original 3/5 s
cap, otherwise twice the cap. Secondary `PAR2_verified_solver_s` counts solver
wall time only if subsequently independently certified. This distinction must
remain visible. A checker can use up to 3 additional seconds offline; those
seconds are never hidden in the end-to-end metric. Parsing, factor detection,
proof generation and process startup remain inside solver timing.

`--suite synthetic --native-only` is a diagnostic, NOT competition evidence.
It tests two coupled parity chains with known SAT/UNSAT outcomes, so that factor
width, reconstruction, certificates and abstention can be inspected.

The old native implementations and main branch are untouched. X1 is not yet
shown to outperform LTM8/R28, Kissat or CaDiCaL on unseen real formulas.

## Explicitly not implemented in v1

No persistent cross-instance training, neural policy, native Gaussian elimination,
XOR extraction engine, GPU kernels, Rust modules, adaptive BDD compilation,
SIMD-accelerated joins, or residual-factor-to-CDCL explanations. CORE learns
conflict clauses only within the current solve. Do not call it trained on prior
benchmarks.

Next experiments should be ablations, not simultaneous rewrites: incremental
factor scheduling; import only independently checkable residual consequences;
bounded separator conditioning; compare dense bitset tables with BDDs; add
selective GF(2) with a certificate path. Keep CORE as a frozen reference and
use family-disjoint, genuinely unused holdout CNFs with 3 repetitions before
claiming a speed improvement. Initial acceptance target: no invalid answers,
at least 5% lower paired verified PAR2, no loss in certified solved count; any
large per-family regression must be explicitly reported.

## Background

- Een and Sorensson, *An Extensible SAT-solver*: https://minisat.se/Papers.html
- Dechter, *Bucket elimination: A unifying framework for reasoning* (1999):
  https://doi.org/10.1016/S0004-3702(99)00059-4
- DRAT proof format/checking: https://github.com/marijnheule/drat-trim

No source code from these SAT solvers is embedded in X1. Using known algorithmic
ideas is different from depending on another solver implementation.


## MEMORY1 research branch: structural before/action/after memory

The branch experiment/drnas-x1-memory1-20261112 adds an **opt-in C++20
structural transition memory** to native X1 CORE. Original core/factor/auto
behavior remains the default. This is not a neural network, an XOR detector,
or evidence of a speedup yet.

Every bounded CDCL decision block records a coarse structural context,
the action (normal or inverted saved decision phase), before/after decisions,
conflicts, propagations, low-LBD clauses, trail length, depth and wall time.
The controller also records a separate terminal outcome. Its measured utility
is a **proxy**, not a proven causal effect or distance to the answer.

The variable-renaming-invariant clause-length and degree/polarity fingerprint
is intentionally coarse (not an exact graph isomorphism test). The persistent
policy contains 16 contexts x 2 arms with sample counts and cumulative scores.
The chosen action can affect decision **polarity only**, never clause validity,
learning correctness, DRUP proofs, SAT model verification, or the termination
status. The transition log is bounded to 2048 detailed JSONL records plus the
final outcome. Persistent state uses a versioned text format.

Example commands:

    g++ -std=c++20 -O3 -DNDEBUG -Wall -Wextra -Wpedantic -Werror research/drnas_x1/x1.cpp -o build/drnas-x1
    ./build/drnas-x1 --mode core --seconds 2 --proof /tmp/p.proof --memory --memory-interval 8 --memory-log /tmp/trace.jsonl --memory-save /tmp/policy.txt instance.cnf
    ./build/drnas-x1 --mode core --seconds 2 --proof /tmp/p2.proof --memory-load /tmp/policy.txt --memory-frozen --memory-log /tmp/frozen.jsonl instance.cnf
    python3 -S research/drnas_x1/memory1_bench.py --binary build/drnas-x1 --out memory1_results

A solver-supplied UNSAT label is never itself ground truth. The benchmark
promotes model state after independent original-CNF SAT/UNSAT verification,
then freezes memory for SHA-disjoint synthetic holdout formulas (three
repetitions). Compare independently verified solved counts and paired end-to-end
PAR2; do not claim a universal benefit, globally blind official data, or a
causal result based on before/after correlation alone.

Next: signed implication graph events, bounded paired probes, factor route
episodes, and proof-preserving extraction of new logical relations.
