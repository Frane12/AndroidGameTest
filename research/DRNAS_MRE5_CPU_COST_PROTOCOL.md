# DRNAS MRE5 — native CPU cost and watched-clause efficiency (experimental)

Date: 2026-11-08
Repository: Frane12/AndroidGameTest
Branch: experiment/drnas-mre5-cpu-watch-cost-20261108

## Targeted question

Why does adding only one or two logically implied binary CRR clauses to
CryptoMiniSat sometimes REDUCE CDCL decisions yet INCREASE total solve time?
Is the difference native process CPU work, irrelevant watched-bin scans,
or just timing/instrumentation noise?

## Source, scope, correctness

Use only the SHA-locked previously tested SAT2026 original:
official-28dcc4119e1bbb5fbd3fdd8f4140f28d.cnf
SHA256 b2c2008e5d24a7aa82499d1486af2550a53a7167e46836c4b9977846204ad483.
2702 declared variables, 8933 original clauses.

Proof-replayed MRE1 derived 8 mathematically sound clauses. MRE2 gate chose:
- A = (-12, 224)  => x12 implies x224
- B = (12, -224)  => x224 implies x12.
They form the equality x12 == x224.

Native source pinned to CryptoMiniSat 5.11.15 upstream commit
3b709118fd08eb1d15f25e0e239dbc596f967b60.
All 32 arms use the same compiled instrumented CMS shared library, all
have OTF Gauss disabled, same source XOR rows, verified original SAT
witness and seed.

Exactly 2 source-paired native seeds x 2 timing repeats x 8 arms:
XOR baseline, A-only, B-only, A+B; EACH run with telemetry ON and OFF.
Do NOT expand to large benchmarks until this study establishes a mechanism.

## Native CPU measurement

Around the native cms.solve() call, read:
- CLOCK_PROCESS_CPUTIME_ID, which counts process CPU seconds;
- getrusage(RUSAGE_SELF) user+system CPU seconds;
- steady_clock solver wall seconds.

This excludes Python proof derivation, Python CNF preparation,
native DIMACS ingestion, XOR addition and SAT witness reconstruction.
Python subprocess wall seconds are captured separately.

### Hot-loop counters

In the actual non-inprocessing PropEngine::prop_bin_cl:
- global visits across all binary watch IDs;
- second literal satisfied (no new assignment),
- second literal undefined (direct unit enqueue),
- second literal false (direct conflicting watcher);
- same event categories tagged to the exact internal watch IDs of A and B.

No per-event printing or OS clock calls in the propagation loop.
When telemetry OFF, a single function invocation returns before any
counter work. This does NOT eliminate every instrumentation instruction.
ON/OFF of identical inputs is intended to quantify its own perturbation.

## Critical interpretation

Paired native CPU difference between, e.g. (A+B)_OFF and XOR_OFF
measures the *end-to-end CPU effect of adding both clauses* on this exact
source and seed, including the changed trail, decisions, branching,
propagation cascades and memory layout. It is NOT the CPU cycles
directly consumed by just those two watcher IDs.

The tagged visits/units/conflicts measure direct native watcher activity,
but do not measure all downstream work causally induced by those clauses.
The ratio of satisfied visits to total visits helps reveal wasted scans,
but many such visits are still normal watched-literal maintenance.

Two repeats are useful to see timing stability; they are not two
statistically independent formula instances. This is NOT a blind holdout
and should never be presented as a general SAT solver performance claim.

## Advance criteria

1. Full SAT witness validation and every native watch ledger passes.
2. All 32 attempts completed with exact source SHA and paired seeds.
3. Only if the CPU delta is stable across both seeds and overhead controls
   is a CPU-performance claim made.
4. Prefer elimination of bad work (MRE3 early guard) over blindly adding
   derived binary lemmas.
