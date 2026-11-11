# ATLAS-X S1 — frozen structured-source experiment

**Frozen before benchmark.** Branch: `experiment/drnas-atlasx-structured-s1-20261111`.

Purpose: discriminate between (a) a correct but irrelevant tiny-relation atlas,
(b) a useful, low-cost local rewrite on genuinely structured sources, and
(c) artificially favorable planted controls. No source selection by observed runtime.

## Sources and exact selection

Eight source IDs selected *before* any solver execution, pinned by the
SHA256 of original SATLIB .tar.gz source archives and deterministic filename SHA
rankings, or by deterministic generator seed:

| shard | cohort | source | frozen selection |
|--|--|--|--|
| 0 | external structured | SATLIB planning logistics | SHA-rank 2 |
| 1 | external structured | SATLIB planning logistics | SHA-rank 3 |
| 2 | external structured | SATLIB graph coloring flat200-479 | SHA-rank 13 |
| 3 | external structured | SATLIB graph coloring flat200-479 | SHA-rank 17 |
| 4 | planted positive control | redundant local relations + XOR | seed 0xA715 |
| 5 | planted positive control | redundant local relations + XOR | seed 0xB37C |
| 6 | planted circuit control | AND, XOR, ITE circuit | seed 0xC5E2 |
| 7 | planted circuit control | AND, XOR, ITE circuit | seed 0xD940 |

Original archives are pinned in
`research/drnas-sat-v7-4/frozen_real_medium.json`, and SHA256 hashes of
normalized source CNF and original archive entry are written into per-shard
`source.json`. Synthetic controls must not be described as previously unseen
*real-world* instances. Planning/GCP files are previously published SATLIB
instances, not strictly blind to all previous DRNAS work; their **source
selection is prospective for this S1 experiment**.

## Fixed benchmark protocol

Five arms: DRNAS native R3C `A`, ATLAS1, ATLASX, pinned Kissat and installed
CaDiCaL. One logical CPU each via `taskset` on the same Actions runner;
8-second time cap; 3 matched repetitions per SHA; 8 shards, thus 120 total
solver runs (24 per arm). Benchmark wall E2E times include executable startup,
preprocessing, and CDCL. Unknown => PAR2=16 seconds. Only SAT answers whose
model independently satisfies original CNF are counted as verified solved.
Any unexpected UNSAT fails closed; none may be called independently LRAT-certified.

The audit MUST separate external originals from planted controls.
Compare PAR2, solved counts, total/paired E2E, `decision=commit/sleep`,
`kind`, `saved_literals`, `l1_checks`, `l2_pairs`,
`l2_implications`, `l2_expansions`, and time budget. The current
ATLASX L0 guard deliberately sleeps when no *exact support* has multiple
clauses. It may miss ordinary three-clause AND gates with smaller-support
binary clauses; this is a **detectability limitation**, not proof of absence
of logical structures.

A measurable speedup on planted controls alone is insufficient. The primary
claim would require improvement on separately verified external structured CNF
sources, prospective duplicates excluded, with neither solver-time selection
nor unsound UNSAT claims. This test is a small pilot and is not statistically
powered to claim broad superiority.
