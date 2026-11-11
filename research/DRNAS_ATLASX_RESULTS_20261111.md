# DRNAS ATLAS-X — implementation and paired results (2026-11-11)

## Provenance

- Experiment branch: `experiment/drnas-atlasx-lazy-extended-20261111`
- All writes isolated to this branch. Stable `main` and ATLAS1's own branch unchanged.
- Initial complete run (before source-only early guard): https://github.com/Frane12/AndroidGameTest/actions/runs/42934561826
- Optimized complete run: https://github.com/Frane12/AndroidGameTest/actions/runs/42934855201
- Latest implementation commit for the optimized run: `08a343a4c71a29c797aaf57af24d530f55ba9a3b`
- Independent C++ native DRNAS R3C CDCL, plus Kissat pinned to `8af8e56f174b778aef3aa45af9f739b2a5f492c2` and installed CaDiCaL.
- One logical CPU per arm; 4 source-selected SATLIB families (rank 24, original SHA), 3 repeats per family, cap 30s, 60s PAR2 timeout penalty. All SAT witnesses checked on the original CNF.

## What was implemented

1. L0 compact 1–4-variable Boolean relation masks, without eager clause materialization.
2. L1 lookup of ATLAS1 generated 2–4-input NPN recipe, with exact truth-table check.
3. L2 joins distinct overlapping local groups over 5–6 variables using lifted truth masks. When one group implies the other, discard it only while retaining the proof context; **no extended CNF expansion** is necessary.
4. L2 optional exact greedy CNF reconstruction on five variables, only with source-complexity and time-budget criteria.
5. All actual rewrites are verified exhaustively for up to 64 assignments before replacing **original** clauses. All non-selected original clauses are preserved; no existential variable removal or SAT model reconstruction.
6. Cheap `L0_no_composite_support` early sleep gate eliminates full-mask/index work and L2 scans if no group has repeated exact support. This is sufficient for current ATLASX reduction rules; it does not claim that there are no other possible SAT reductions.

## Correctness checks

- 300 randomized small-CNF full truth-equivalence checks: **pass**; 93 runs committed some exact rewrite.
- Targeted L2 implication deletion: **pass**, 8 literals removed in an exact synthetic example.
- Targeted L2 on-demand expansion: **pass**, 9 literals saved in an exact synthetic example.
- Unrelated source blocks: **pass**, slept without rewriting.
- These checks validate Boolean equivalence of individual candidates, not independent LRAT certification for UNSAT.

## First completed holdout (before early sleep gate)

| Solver | SAT solved (12) | PAR2 total seconds |
| --- | ---: | ---: |
| CaDiCaL | 12 | 1.694691 |
| Kissat | 12 | 1.753697 |
| DRNAS A clean | 12 | 3.622477 |
| DRNAS ATLAS1 | 12 | 3.629829 |
| DRNAS ATLASX | 12 | 3.695864 |

All four source-only rank-24 problems returned `sleep`; ATLASX did not find a profitable rewrite. Preprocessing took ~2.3–2.9 ms and ATLASX showed ~2.0% aggregate time regression to its paired native baseline.

## Final completed optimized holdout (after early sleep gate)

| Solver | SAT solved (12) | PAR2 total seconds |
| --- | ---: | ---: |
| CaDiCaL | 12 | 1.517508 |
| Kissat | 12 | 1.657118 |
| DRNAS A clean | 12 | 3.677776 |
| DRNAS ATLAS1 | 12 | 3.679959 |
| DRNAS ATLASX | 12 | 3.681070 |

ATLASX / DRNAS clean aggregate PAR2 = **1.000896**, i.e. approximately **0.09% slower** on this small sample; a practical tie within normal benchmark noise. ATLASX / ATLAS1 aggregate PAR2 = **1.000302**, likewise near tie. Do not claim an established solver speedup.

Per-family PAR2 totals (three repetitions for each):

| Original SATLIB | DRNAS A | ATLAS1 | ATLASX | Kissat | CaDiCaL |
| --- | ---: | ---: | ---: | ---: | ---: |
| uf100-430 | 0.023397 | 0.024082 | 0.023295 | 0.073825 | 0.026767 |
| uf150-645 | 0.305410 | 0.306537 | 0.317888 | 0.110320 | 0.027963 |
| uf200-860 | 2.036504 | 2.041211 | 2.035302 | 0.574016 | 0.140647 |
| uf250-1065 | 1.312465 | 1.308129 | 1.304585 | 0.898957 | 1.322131 |

On all four rank-24 source formulas the optimized path identified `L0_no_composite_support`, skipped mask construction, and performed **zero** L2 expansions. First-repeat preprocessing costs were **0.170, 0.249, 0.339, 0.222 milliseconds**, respectively. The earlier code spent ~2.3–2.9 ms. Comparison of preprocessing time is indicative, not a controlled claim about speedup across GitHub runners; compare paired E2E within each workflow run.

## Assessment and next falsifiable step

The requested lazy architecture **works and is source-equivalent on tested modules**. It is not yet shown to outperform standard preprocessing on realistic structured instances. The current random SATLIB holdout is a negative structural control; all candidates slept. Test new SHA-frozen structured CNFs with repeated gate supports / adjacent multi-clause modules, while preserving separate 1CPU E2E PAR2, solved count, exact SAT model checks, and independent proof verification for any UNSAT claim. Avoid leakage or selecting winners after benchmark outcomes.
