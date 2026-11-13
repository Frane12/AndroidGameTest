# COOP1 local first-build results

Code commit: `7b9a33fefb7a12fd89f44804467d53880b0e80d0`. No solver tuning after either benchmark.

Safety: 1,776 oracle comparisons; 484 independently checked UNSAT proofs; 3,526 independently checked RUP steps. All passed. Frozen X5_NO_MIN and COOP_OFF additionally matched search statistics and models on 12 distinct random CNFs.

Smoke: all 420 attempts verified. ON was slower overall; inputs were mostly too easy for reliable timing conclusions.

Stress: 42 formulas in 7 families, 2 repetitions, 5 arms, 1 s end-to-end cap, one logical CPU. Each arm has 84 attempts. PAR2 values below are sums; smaller is better.

| Arm | Verified within cap | PAR2 sum (s) | Lemmas | Branch changes |
|---|---:|---:|---:|---:|
| X5_NO_MIN | 56/84 | 59.6934 | 0 | 0 |
| COOP_OFF | 56/84 | 59.4855 | 0 | 0 |
| COOP_OBSERVE | 57/84 | 58.8669 | 0 | 0 |
| COOP_ALGEBRA | 58/84 | 58.2792 | 4177 | 0 |
| COOP_ON | 57/84 | 58.7333 | 4497 | 668 |

Algebra-only reduces aggregate PAR2 by 2.03% versus same-binary OFF; family-cluster bootstrap interval: -11.0% to 24.5%. This does not establish a reliable global gain.

The clearest mechanism signal is sparse XOR SAT: algebra 11/12 versus OFF 8/12, with PAR2 3.9400 versus 8.2157 s. General random-3SAT and overhead regressions remain. The full ON mode is not better than algebra-only overall.

OBSERVE solved one extra timeout-borderline pigeonhole attempt despite identical search policy. This illustrates timing variability and precludes attributing every solved-count change to the algorithm.

No incorrect accepted SAT model or UNSAT proof. Main and frozen sources unchanged. No real-formula superiority or promotion is claimed. The independent GitHub run is https://github.com/Frane12/AndroidGameTest/actions/runs/43476198427.

Machine-readable report, frozen input manifest and every paired trial are adjacent to this file. Full CI proofs, models and binaries are retained in the workflow artifact.
