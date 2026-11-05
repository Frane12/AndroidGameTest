# DRNAS R150 — dubinska analiza uzroka regresija (2026-11-05)

**Status:** retrospective diagnosis of a COMPLETED prospective run; **NOT** a new blind validation, and **NOT** an upgraded solver.

## Provenance and protocol
- Original benchmark: https://github.com/Frane12/AndroidGameTest/actions/runs/42088721067
- Frozen test: 55 original SHA-verified CNFs (20 official2026, 15 official2025, 10 miter, 10 cryptography); 2 repetitions, 15-second cap, 8 shards; modes: Kissat, CaDiCaL, R148, R150_02, R150_07.
- 550 complete trial records, 8/8 successful shard jobs, final audit successful.
- SHA-disjoint from historical 400 training CNFs and R132-125, **not** exhaustively disjoint from every older DRNAS evaluation.
- Formula identifiers below are stable IDs **within this run**. The original manifest and all raw paired rows are in artifact `DRNAS-R150-NEW-EXTERNAL-PROSPECTIVE-FINAL`.
- SAT witnesses checked on original CNF; UNSAT claims lack independent LRAT/FRAT certification. Multiple CPU models across GitHub shard runners; each formula's 5 modes nevertheless run paired within the same shard.
- This report is for diagnosis; the 55 cases have now been exposed and cannot be reused as a fresh blind benchmark for a revised selector.

## Final PAR-2 (seconds; lower is better)
| Mode | Solved / 110 | Timeouts | PAR-2 | Detector total |
|---|---:|---:|---:|---:|
| Kissat | 38 | 72 | 2250.374148 | 0 |
| CaDiCaL | 34 | 76 | 2327.159767 | 0 |
| R148 | 36 | 74 | 2288.064031 | 0.687769 |
| R150_02 | 36 | 74 | 2281.902753 | 1.172058 |
| R150_07 | 36 | 74 | 2288.317108 | 1.160546 |

- R150_02 reduces R148 PAR-2 by 6.161278s (~0.2693%), but is worse than Kissat by 31.528605s (~1.4010% of Kissat PAR-2) and solves 2 fewer attempts.
- R150_02-vs-R148 stratified bootstrap 95% interval reported by audit: [-0.044348%, +0.722057%]. Improvement is not statistically established.
- R150_02 has 1 >=2x regression versus R148. No promotion.
- R150_07 never overrides R148; it spends additional detection time with no evident benefit.

## Exact origin of poor aggregate versus Kissat
Two inherited R148 policy errors dominate.
| Frozen identifier | Cohort | Kissat PAR-2 across 2 reps | CaDiCaL PAR-2 | R148 PAR-2 | R150_02 PAR-2 | Base => R150_02 | R150 score |
|---|---|---:|---:|---:|---:|---|---:|
| official2026-000.cnf | official2026 | 19.307 | 60.000 | 60.000 | 60.000 | CaDiCaL => CaDiCaL | +0.016609078 |
| official2025-004.cnf | official2025 | 20.6897 | 60.000 | 60.000 | 60.000 | CaDiCaL => CaDiCaL | +0.022155888 |

These two account for ~80.003s of R150_02's 31.529s total deficit versus Kissat. This is **diagnostic post-hoc attribution**, not permission to omit these problems from metrics or to hardcode identifiers. The R148 frozen selection chooses CaDiCaL on fully scanned sparse/non-Horn cases (binary_fraction<0.30 and horn_fraction<0.55), which does not reliably imply CaDiCaL will solve before the cap. The R150 ridge score is positive in both cases, so neither 0.02-threshold override corrects the inherited error.

## Breakdown by source cohort
| Cohort | # formulas | Kissat PAR-2 | R148 PAR-2 | R150_02 PAR-2 | R150_02 solved / # trials |
|---|---:|---:|---:|---:|---:|
| cryptography | 10 | 340.472048 | 297.543892 | 291.287975 | 12/20 |
| miter | 10 | 181.000436 | 181.446468 | 181.503542 | 14/20 |
| official2025 | 15 | 624.762709 | 664.227392 | 664.243314 | 8/30 |
| official2026 | 20 | 1104.138955 | 1144.846279 | 1144.867922 | 2/40 |

R150's tiny gain is from cryptography only (+6.256s vs R148), while miter, official2025 and official2026 yield no substantive gain. In official2025/2026, two inherited solver selection failures determine most of the difference versus Kissat.

## Causal changes versus inherited policy
- R150_02 overrides the R148 route on **13 formulas (26 trials)**. Every override is **Kissat => CaDiCaL**; none is CaDiCaL => Kissat.
- Two beneficial changed formulas:
  - `cryptography-006.cnf`: R148 5.2086s vs R150_02 1.3369s; benefit ~3.872s; pure CaDiCaL 1.3211s.
  - `cryptography-003.cnf`: R148 15.9428s vs R150_02 13.0032s; benefit ~2.940s; pure CaDiCaL 12.9899s.
- Two harmful changes:
  - `cryptography-004.cnf`: R148 ~0.0969s vs R150_02 ~0.1939s (~2.00x).
  - `cryptography-002.cnf`: R148 ~0.0713s vs R150_02 ~0.1397s (~1.96x).
- Other **9 overridden formulas** have both candidate backends at 30+30s PAR-2 timeout, thus no observable solver benefit.
- Aggregate R148=>R150_02 gain on 13 changed formulas: +6.645987s. On remaining 42 unchanged-route formulas: -0.484709s.
- Additional R150_02 detector cost compared to R148: 1.172058 - 0.687769 = **0.484289s**; closely matches the loss on unchanged-route formulas, consistent with the cost of a second native feature extraction process.
- 35/55 formulas have Kissat/CaDiCaL both timing out (60s PAR-2 over 2 trials); a 15s cap leaves many structural decisions **unidentifiable**.

## Mechanism demonstrated by source
1. `research/r148_exact_fast_selector.cpp` implements frozen R135 route: CaDiCaL iff fully scanned <8MiB / <120k clauses with binary_fraction<.30 and horn_fraction<.55; otherwise Kissat.
2. `research/r150_features.cpp` builds 16 fixed, clipped [0,1] features from at most **256 KiB / 4,096 clauses**, including header-based counts, binary/Horn/dual-Horn proportions, degree and binary implication fanout proxies. These are only prefix statistics and miss late heterogeneous structures, XOR rank, conflicting cores, and dynamical solver behavior.
3. `research/r150_quality_benchmark.py` launches R148 extraction first, then launches a **second** R150 feature subprocess, then the selected backend. R150_02 has median detector ~9.239ms vs R148 ~5.014ms.
4. The model is ridge regression trained from 400 earlier exposed formulas, with a clipped target `clip((Kissat_PAR2 - CaDiCaL_PAR2)/15, -1,1)`, L2 regularization 8, and fixed thresholds .02/.07. Retrospective 5-fold cross-fitting already measured **negative** gains: threshold .02 -> -13.251305s and 1 >=2x regression from 25 route changes; threshold .07 -> -5.722457s from 1 change.
5. **Collision in scalar predictions:** `cryptography-002.cnf`, `-003.cnf`, `-006.cnf` all receive score +0.04727334 but Kissat wins -002, while CaDiCaL wins -003 and -006. The scalar score cannot distinguish them (not a proof that all 16 raw features are identical). This is direct evidence that the model's current representation/decision score is insufficient.
6. All actual route overrides are in the same direction; a positive margin cannot rescue already selected CaDiCaL instances for which Kissat is dramatically faster. This is a **policy-coverage** failure, not just CPU overhead.

## Research conclusion: do NOT tune against these 55 formula IDs
- No CI/build bug found; benchmark successfully completed. These are structural decision and statistical validation problems; do not patch the stable baseline.
- Highest priority is a **symmetric regret-based, abstaining selector** that can safely override CaDiCaL => Kissat as well as Kissat => CaDiCaL, trained on appropriately separated sources. Train targets should explicitly encode timeout-vs-solved losses (PAR-2 regret), weight high-severity errors, and require positive out-of-fold expected gains net of detection cost.
- Avoid another single-pass 256 KiB-prefix-only linear score. Compare a bounded, genuinely informative signal (prefix+reservoir segment sampling; binary implication graph distribution; cheap XOR pattern certification) with a *single-process* native implementation. Acknowledge that expanded feature extraction can become expensive; impose explicit overhead cap.
- Use grouped leave-family/competition-year-out validation, robust uncertainty estimates, and cost-sensitive abstention to Kissat absent decisive evidence. Never train and validate the route on the same formula SHA or closely duplicated instances.
- Pre-register a **NEW** balanced SHA-disjoint cohort, separate from both the historical 400 and these exposed 55, with same hardware/caps/seeds and paired Kissat/CaDiCaL/best frozen DRNAS controls, plus 15s and longer-cap diagnostic strata. Log route, score, features, selector overhead, SAT witnesses, independent UNSAT proofs if available, solved, timeouts, PAR-2 and >=2x regressions. No cherry-picking easy cases.
- Only consider promotion if new blind holdout and repeated runs show reliably improved PAR-2 **and** no solved-count or correctness/stability regression.

This note is for reproducible diagnosis; no new solver build/run was triggered.
