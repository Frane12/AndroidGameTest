# DRNAS SAT R27b — native restart risk gate: multi-family generalization audit

Date: 2026-11-03
Final full run: https://github.com/Frane12/AndroidGameTest/actions/runs/41609273740
Final artifact: https://github.com/Frane12/AndroidGameTest/actions/runs/41609273740/artifacts/13218222145
State: **Negative result: no evidence of general advantage. Do not promote R27 to stable solver.**

## Reproducible protocol

- SHA-pinned Kissat commit: 8af8e56f174b778aef3aa45af9f739b2a5f492c2.
- Every strategy uses the **same native instrumented binary**, matched original input and CPU affinity within each runner; this is **not** a clean, noninstrumented upstream Kissat comparison.
- 72 synthetic CNF formulas in six fixed families (12 each); 2 paired repeats × 5 native modes = 720 completed trials; 2 s limit, PAR-2 timeout penalty 4 s; all four shards and final audit passed.
- Fixed native R27 policy reads live metadata at conflict 4096: mature-low-LBD antecedent share < 0.15, fast-to-slow glue ratio >= 1.0, and restarts >= 8, otherwise abstains. The hypothesis was motivated by the earlier known R26 examples and frozen before the first R27 run.
- R27b is a repair of the **research sidecar telemetry**, not a newly trained selector: the sidecar clause-birth hash capacity was raised from 2^18 to 2^20 and saturation changed from a fatal exit to an unknown-age counted fallback. Original R27 attempt failed on a hard Tseitin UNSAT case with \`R21_BIRTH_TABLE_FULL\`. The original attempt also contained an artifact folder aggregation bug, now repaired.
- Because the same R27 formulas were partially evaluated before R27b's infrastructure repair, this is a *replay with frozen policy*, not an untouched blind holdout at the time of the repaired run. It remains SHA-distinct from the earlier R24/R26 development cases.
- SAT witness assignments were verified against original clauses; independent UNSAT proof certificates were not checked. XOR parity-generator cases have mathematically known expected status.

## Full aggregate (144 attempts per arm)

| Native action | Total PAR-2 (s) | Cases solved in both repeats | Timeout attempts | Gain vs monitor |
|---|---:|---:|---:|---:|
| Monitor / no intervention | 104.523776 | 64/72 | 16 | baseline |
| Force restartint 25 at conflict 2048 | 107.172064 | 63/72 | 18 | -2.534% |
| Force restartint 50 at conflict 2048 | 114.412795 | 62/72 | 20 | -9.461% |
| Force restartint 50 at conflict 4096 | 110.786370 | 63/72 | 18 | -5.992% |
| **R27 cautious guarded 4096→50** | **109.416983** | **63/72** | **18** | **-4.681%** |

R27 reached its decision checkpoint in 84 of 144 attempts but actually switched in just **4 attempts** across **2 formulas**, both in the XOR family. One formula regressed by more than 2× under PAR-2.

## Per-family R27 vs monitor

| Family (12 formulas ×2 repeats) | Monitor PAR-2 (s) | R27 PAR-2 (s) | R27 gain |
|---|---:|---:|---:|
| random 3-SAT, 220 vars, density 4.23 | 21.351034 | 21.427260 | -0.357% |
| random 3-SAT, 280 vars, density 4.23 | 64.259531 | 64.248776 | +0.017% |
| random 3-SAT, 220 vars, density 3.85 | 1.117638 | 1.117485 | +0.014% |
| random 3-SAT, 220 vars, density 4.65 | 9.330935 | 9.302312 | +0.307% |
| community 3-SAT, 220 vars | 1.966030 | 1.966504 | -0.024% |
| **Tseitin XOR parity, 64 vertices** | **6.498608** | **11.354646** | **-74.724%** |

Small apparent gains in groups where R27 never switches are timing noise/measurement overhead, not algorithmic improvements.

## Most informative failed case

\`tseitin_xor_64_10.cnf\`, parity UNSAT:
- Monitor: 1.587509 s median, 2/2 UNSAT.
- Native R27 gated 4096→50: timeout 2/2; PAR-2 = 4.0 s per attempt.
- Forced 2048→25: 0.841012 s median, 2/2 UNSAT.
- Forced 2048→50 and forced 4096→50: timeout 2/2.
- The frozen guard selected precisely the 4096→50 action that harmed this formula.
- Paired ratio using penalized PAR-2: 4.0 / 1.587509 = 2.520×. The actual completion time under the harmful action is unknown, only exceeds the 2 s cutoff.

A second XOR case (\`tseitin_xor_64_04.cnf\`) was selected and slowed moderately: 0.120040 s → 0.134364 s.

## Interpretation and next hypothesis

- The R27 generalization claim **fails** on this evaluated suite; reject promotion to stable DRNAS V15.3.1.
- One-dimensional thresholds over summary early dynamics are insufficient to reliably choose between restart intervals, especially for structured parity/XOR graphs.
- The fixed 2048→25 portfolio arm was 17.897% better on the Tseitin XOR subset but **2.534% worse overall**, so neither global 25 nor global 50 is a universal solution.
- The fixed 2048→50 arm was +5.78% on random3 280-variable critical-density subgroup but -9.461% overall; distribution-specific trade-offs remain.
- R28 research suggestion: recognize exact GF(2) parity structure using a correctness-checked structural front end and choose strategies only after frozen independent development; add out-of-distribution official SAT Competition instances and fresh SHA-distinct synthetic cases. Keep safe fallback and instrument overhead included. Do not tune and re-use this same R27 cohort as fresh holdout.

This is a **finite empirical result** in algorithm engineering, not a statement about P vs NP or universal SAT complexity.
