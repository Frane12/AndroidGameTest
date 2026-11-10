# DRNAS Native Core R2B — original-CNF causal GF2 audit
Date: 2026-11-10
Code and CI branch: `experiment/drnas-native-core-r2b-xor-selection-20261110`
Successful independent mathematical QA and 16 real-CNF oneCPU benchmark:
https://github.com/Frane12/AndroidGameTest/actions/runs/42840736894

## Actual native implementation
`research/drnas_native_core_r2b.cpp` is a from-source standalone C++17 SAT solver, extending the user's original R1 CDCL: 2-watched BCP, 1-UIP resolution, nonchronological backtracking, native variable activity and restarts. No third-party SAT solver libraries or subprocess calls.

GF2 source rows are accepted only after verifying that every forbidden-assignment CNF clause of the complete parity block (arity 2–4) is present on the *original* formula. The GF2 sum of two independently certified rows is also original-CNF entailed. An inferred XOR unit is delivered through an own SAT clause on the native CDCL trail, with a corresponding complete reason clause; a violated parity would produce a native 1-UIP conflict reason.

R2B corrects R2's structural-selection weakness: independently source-certify **up to 1,024** original XOR candidates, derive short GF2 sums from the whole certified pool, and activate at most 128 source rows and 64 derived rows per original. Both native clauses and proofs have no foreign SAT dependency. Keep a 500,000-XOR-evaluation budget with safe off-switch.

## Correctness
- C++ R2B exhaustive truth-table internal tests **1,636/1,636 correct** (516 SAT and 1,120 UNSAT).
- Separate Python independent truth-table testing **600/600** (240 random small formulas x 2 modes + 120 intentionally overlapping XOR cases), including **120/120** cases where the derived parity consequence must enter real native CDCL.
- R1, R2 and R2B compiled with C++17 standard library only. No CaDiCaL, Kissat, CryptoMiniSat, or other SAT solver binary linked or invoked.

## Strict 2-SHA original E2E pilot
Two original source-preregistered MIXAB3 SHA from NOVEL2C mathematical source-only scan; these exact SHA were selected before this R2B timing experiment. Both previously seen, not blind:
- `daa0360a834fbd9f49437d2b3fd6b372d331774100d913d55c57c0de547eb623`, previously 20 reductive binary GF2 candidates in the 32-row external detector.
- `e3e6b2c71ca07f5f17491a38490b29fb63045be258ad6837bcc4530b31438162`, previously 16 candidates.

Original SHA matched, all attempts 6-second E2E wall cap, same one logical CPU, two repeats x four **own** source-built solver variants = 16 trials. No independent original-CNF LRAT, so raw UNSAT would be excluded from strict PAR2.

| Arm | trials | SAT verified | raw UNSAT | timeout | PAR2 strict s | total wall E2E s | derived rows max | derived GF2 implications | completed GF2 clause reasons |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Native R1 | 4 | 0 | 0 | 4 | 48.0 | 24.027020 | 0 | 0 | 0 |
| Native R2 GF2 | 4 | 0 | 0 | 4 | 48.0 | 24.027055 | 39 | **24** | 24 |
| Native R2B plain | 4 | 0 | 0 | 4 | 48.0 | 24.026197 | 0 | 0 | 0 |
| Native R2B GF2 | 4 | 0 | 0 | 4 | 48.0 | 24.027655 | 64 | **50** | 50 |

On `daa036...` the R2B source detector certified 380 original rows, activated 128, derived 64 rows, delivered four GF2 consequences per repetition (versus R2 eight).

On `e3e6b2...` the detector certified 618 original rows, activated 128, derived 64, delivered 21 GF2 consequences per repetition (versus R2 four).

Thus R2B produced **2.08× more GF2 derived trail implications** overall than R2 (50 vs 24) on this specific matched cohort. There was **NO additional solved original instance**; benchmark strict PAR2 is tied at 48 s on all arms. Never claim solver-time speedup from propagation count alone.

## Decision
- The user's own native CDCL + GF2 is **functional and mathematically validated**, and the R2B source-selection change causes extra live implications on original formulas.
- Not a competitor to Kissat/CaDiCaL yet: simple R1-like CDCL remains hard-limited, cannot solve these selected instances under cap.
- Next engineering priorities: instrument whether GF2 clauses reduce actual *conflicts* or tree size; increase quality and novelty of reasons, avoid redundant GF2 scans, add proof-checkable original UNSAT certification, optimize clause database/restarts/branching and source-only holdouts.
- Preserve R2B strictly experimental; keep `main` and all reference source hashes unchanged.

GitHub Actions source: https://github.com/Frane12/AndroidGameTest/actions/runs/42840736894
