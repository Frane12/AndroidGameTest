# DRNAS SAT R32 — official 2026 input-gate risk notebook (2026-11-03)

## Provenance and experimental status

- Run `41623038027`: 14-source SHA verification and read-only preflight passed; benchmarking shards failed **only** from an incorrect artifact unzip path. This run has no paired timing results.
- Fixed the artifact archive root with commit `62d8acbe184c63d44c1edb276fbaa94165f257e8`; replacement run `41623227197` started. Do not infer timing results from unfinished workflows.
- 14 original Main-track SAT Competition 2026 GBD CNFs, normalized without editing clauses, reused from previously frozen R28 source run `41614909924`. The four synthetic controls are excluded. These 14 are **previously seen**, not a blind holdout. Every selected benchmark currently belongs to the `mp1-Nb*T*.cnf.xz` family; this is not diverse enough to establish general SAT gains.
- Baselines: original pinned Kissat, CaDiCaL 3.0.1, unchanged R29 shadow and unchanged R29 active; 60 s wall cap per attempt, PAR-2=120 s; two deterministic paired orders per formula; same SHA-pinned original CNF per comparison.
- R32 read-only prefix scanner is NOT a new integrated solver and can never change a SAT/UNSAT conclusion.

## Confirmed gate diagnosis from first official preflight

- **13/14 inputs** fell into `R29_ROUTE fallback reason=input_guard`, mostly because `vars > 3000`. Five of those also exceed `150000` clauses. None exceeded the 12 MiB file-size limit.
- **1/14 inputs**, `mp1-Nb5T07.cnf.xz`, had 2608 variables, 10800 clauses and 175211 decompressed bytes. It passed input limits, detected 1125 full parity groups, then returned `fallback reason=no_validated_action`. No certified beneficial intervention was applied.
- The prefix scan stopped at at most 15000 clauses per input (thus on 13/14 inputs it was a sample, not the full problem); its observed cost was about 0.04–0.06 s per input in the first CI preflight, and its full parity group counts do not measure SAT performance.
- Most other official inputs already contain numerous complete parity patterns in the sampled prefix, but R29 never evaluates them because its parser guards terminate early.
- No wrong answer or crash was demonstrated by the first preflight. Performance impact awaits the replacement paired benchmark.

## Conditions before activating an R32 wide-input analyzer

1. **Keep the original fallback invariant.** A size-cap hit, parse error, missing proof, OOM risk, timeout or contradictory observation must call unchanged pinned Kissat on the original input, not guess a result.
2. **Separate cheap gate from algebra.** Avoid dense `O(n × ceil(n/64))` bit-matrix setup or excessive clause-group allocations on official large instances before deciding that a bounded XOR analysis is worth the cost. Record gate runtime and memory separately from solve runtime.
3. **Do not turn partial/near-complete parity signatures into equations.** Full required sign-mask coverage on the same distinct-variable tuple is required. Auxiliary resolution must be explicitly validated against original clauses, including parent IDs, polarity, tautology checks and original-model reconstruction.
4. **Do not claim SAT from a consistent XOR subset of a mixed CNF.** A SAT answer needs an assignment satisfying every original clause; UNSAT from XOR requires a checked row certificate and resolution provenance. A completion certificate may be needed for official Main Track proof rules.
5. **Bound resource usage.** Limit bytes scanned, candidate groups, equations, proof-memory, time spent in GF(2), and number of added implied units; use a memory-aware, sparse-first or indexed approach. Never blindly lift `n <= 3000` to `n <= 60000` without profiling.
6. **Protect wall-clock benefit and correctness.** Compare R32 shadow/active with exactly the same frozen CNF, pinned reference solver, seed/order, timeout and CPU setting. Include preprocessing overhead, fallback percentage, timeouts, >2× regressions and PAR-2, not just the best speedup.
7. **Use diverse NEW official benchmark families.** The currently archived cohort is only `mp1`; expand using provenance-verified 2026 GBD families and an unopened SHA-frozen holdout. Keep retrospective and blind results separate.
8. **No world ranking from these experiments.** Official SAT Competition runs differ in hardware, full cohort, time budget, scorer and mandatory proof checking. Use official published per-instance records only as contextual comparison, not interchangeable wall-clock numbers.

## Next R32 engineering step

Implement an opt-in **read-only streaming gate** for huge valid CNFs, then a bounded proof-producing XOR extractor only on high-confidence subregions. First use shadow mode on untouched official inputs; release active mode only after independently checking any newly derived unit/equation against original clauses and verifying no correctness regressions.