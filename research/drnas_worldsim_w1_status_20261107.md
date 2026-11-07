# DRNAS SAT — current verified results, 7 November 2026

The previously failed SAT2026 summary was recovered from all eight original completed shard artifacts. No solver was rerun. Recovery run: https://github.com/Frane12/AndroidGameTest/actions/runs/42397916379. Original run: https://github.com/Frane12/AndroidGameTest/actions/runs/42396350093.

## Paired PAR-2 comparisons

Ratios are baseline PAR-2 / candidate PAR-2. They describe a penalized benchmark score, not literal CPU acceleration on every formula. All experiments below had a 20s attempt cap; timeout = 40 PAR-2 seconds. Attempts include repetitions.

| Experiment | Original formulas | Candidate | Solved attempts | vs native Kissat | vs native CMS |
|---|---:|---|---:|---:|---:|
| TA3 official SAT2026 | 24 | unchanged TA3 portfolio | 10/48 | 1.077784× | 1.089069× |
| TA3 SAT2025 | 24 | TA3 portfolio | 14/48 | 1.085565× | 1.094934× |
| TA4 SAT2025 | 15 | TA4 pilot | 8/30 | 1.074677× | 1.106412× |
| R199 SAT2025 | 40 | R28+Kissat | 36/120 | 1.034900× | 1.070863× |

## Recovered official SAT2026 detail

| Arm | Solved attempts / 48 | Distinct solved / 24 | PAR-2 total seconds | Capped elapsed total seconds |
|---|---:|---:|---:|---:|
| TA3 portfolio | 10 | 5 | 1582.844897 | 822.844897 |
| R28+Kissat | 8 | 4 | 1625.788390 | 825.788390 |
| native Kissat | 6 | 3 | 1705.965230 | 865.965230 |
| native CMS | 6 | 3 | 1723.827576 | 883.827576 |

The 24-source set includes known R115 source 75429ff7acb5acb597abe01aa745c2a6. It must not be called globally unseen. Removing that known formula as a clearly labeled sensitivity analysis gives TA3 8/46 solved attempts and PAR-2 1582.821440s; Kissat 6/46 and 1625.965230s; CMS 4/46 and 1717.292667s. Corresponding ratios are about 1.0273× and 1.0850×. This is an exclusion analysis, not a replacement headline test or a new holdout.

Formula-cluster bootstrap, 24 formulas and 10,000 resamples, seed 20261107: 95% ratio intervals 0.9681–1.2615 versus Kissat and 0.9998–1.2462 versus CMS. Neither establishes general superiority.

There is a substantial routing regression: source 6d815089fb4095208754622b4c44a8f7 routes to CMS and takes a mean 13.824438s, whereas native Kissat takes 0.4416635s (approximately 31.3× faster). The 60s WorldSim method remains frozen; this observation is a future-development lead and must not tune the ongoing evaluation.

On the known R115 source, TA3 including profiling takes a mean 0.0117285s; CMS takes 3.2674545s and Kissat times out at 20s in both repeats. These are a targeted approximately 278.6× CMS ratio and at least 1705× against capped Kissat, not whole-suite speedups.

Historical same-source R115 without TA3 profiling: R28 median 0.002698s versus CMS+Gauss 3.196462s = 1184.8× in run https://github.com/Frane12/AndroidGameTest/actions/runs/42379705361. Known pure-XOR control only.

TA4 improves its TA3 control by only 0.073% PAR-2 (0.699632 seconds total), with the same 8/30 solved. TA3 remains the better-supported WorldSim primary. TD2 is development-exposed and TK mixed active mode is slower, so neither is promoted.

## WorldSim W1 is running

Run: https://github.com/Frane12/AndroidGameTest/actions/runs/42397824391
Code and frozen protocol: https://github.com/Frane12/AndroidGameTest/blob/c9d17759d3c941141a8d0f028d923e1c1f066197/research/drnas_worldsim_w1.py

- All 24 frozen official SAT2026 originals; six configurations; three repetitions; 60s end-to-end attempt cap; 432 attempts; eight source-disjoint shards.
- TA3, R28+Kissat, Kissat 4.0.4, CryptoMiniSat 5.11.15, CaDiCaL 3.0.1, official 2026 satsuma-iter+kissat entrant. The entrant is not labeled world champion without verified ranking evidence.
- Single CPU affinity inherited by all children, sequential randomized paired runs, source/code/binary SHA pins, SAT models verified against original clauses.
- Every CDCL backend requests proof output, including R28 fallback. CMS emits FRAT and other backends their native proof format; independent proof checking is not yet part of W1. The R28 algebraic fast path may have no standard proof file. Generic UNSAT is consistency checked.
- The initial default-command W1 run was superseded before final scoring because the official wrapper wrote proofs while controls did not. The replacement aligns proof requests and corrects the submitted wrapper's proof-file argument.
- All six arms passed SAT and UNSAT smoke checks. Complete-pair audit, incorrect-model rejection, result/exit consistency and process deadline checks passed locally. Final ranking requires all 432 trials, with timeouts retained.
- This is a reduced-budget unofficial simulation on a resource-bounded, repeated cohort. Official sequential competition uses 5000s, a larger set and proof verification. W1 cannot establish a world record or official rank.

Official rules: https://satcompetition.github.io/2026/nhr.html ; https://satcompetition.github.io/2026/rules.html
