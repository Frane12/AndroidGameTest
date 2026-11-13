# X5_NO_MIN: global policy and persistent exact-result cache

Branch: `experiment/drnas-x5-memory-ab108-20261113`.
Base: `7544461ccac6d9f6427b6a43ab0ce6f2bab14148` (DIVERSE72).
The native solver source and frozen reference binaries are unchanged.

108 original CNFs: 96 newly generated medium/larger formulas in 12 balanced
SAT/UNSAT categories and 12 original SAT2024 families selected by size and
SHA-deduplicated, without outcome screening. Synthetic and retrospective
competition results are reported separately. All arms use a single logical
CPU, serial randomized arm order, a 5 s end-to-end cap and PAR2 timeout penalty.
Three shards each own disjoint formulas. There are 1944 measurements.

| Arm | Native policy | Application result cache |
|---|---|---|
| BASE | X5_NO_MIN | off |
| GLOBAL | X5_NO_MIN + frozen global X46COST1 policy | off |
| CACHE | X5_NO_MIN | on |
| GLOBAL_CACHE | X5_NO_MIN + frozen global X46COST1 policy | on |
| PROBE | X5_NO_MIN + same 8-conflict probe, without learned policy | off |
| CORE | Frozen original control | off |
| Kissat / CaDiCaL / CMS | Frozen standard references | off |

The global database is pinned at commit
`b1e738d9ff5eacd6a1e1dac57957afc6ee4ba746`. The exact model is exported
from SQLite and hash-checked before any evaluation. It is an **experimental
transfer of an X46-trained model**, previously rejected for deployment;
it is not an X5-trained or promoted champion. No new training, shared database
write, or automatic model promotion occurs. Original SHA overlap with the
model's training and validation is rejected. One-time decompression/export
cost is reported separately; the native model load is inside every uncached solve.

Cache means a bounded, persistent SQLite store of **exact formula results and
their certificates**. It is not CPU cache, heuristic pattern learning, or
logical clause sharing between different formulas. Keys include the exact
original CNF SHA and the binary/model/policy identity. Only verified SAT
witnesses or independently checked DRAT proofs enter it. Each arm owns its
own cache, starts empty, completes a cold pass, closes and reopens SQLite,
then performs a warm pass over the same formulas. Unsolved cases remain misses.
Entries over 8 MiB are skipped; payload total is bounded to 64 MiB per arm.
Cache reading, writing and certificate rechecking are inside the timed budget.
On each hit the original formula is hashed and its certificate reverified.
Cache creation is one-time setup. Solver RSS excludes Python/SQLite and is
not a claim about total cache RAM; cache file sizes are reported separately.

Cold and warm results are never pooled for generalization claims. An exact
repeat cache win says nothing about solving unseen formulas. The report gives
paired source-SHA bootstrap intervals, solved parity, per-family regressions,
model loads, probe triggers, flips, cache hits and stores. Repetitions are not
treated as independent source samples. Both main effects can be inspected:
GLOBAL versus BASE/PROBE, and CACHE versus BASE / GLOBAL_CACHE versus GLOBAL.

Validation covers all twelve categories, cold misses, persisted SAT and UNSAT
hits, source/policy isolation, checksum corruption and forged SAT witnesses.
The full report fails closed on missing arms, sources, shards or invalid proofs.
