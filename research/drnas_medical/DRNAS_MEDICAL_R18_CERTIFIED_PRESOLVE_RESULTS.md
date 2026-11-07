# DRNAS Medical R18 — Certified pre-solve wildtype-flux prediction

**Date:** 2026-11-07  
**Research question:** Can a single feasible wildtype metabolic flux, incorporated into source-only GPR/network features **before any candidate solving**, predict the number of LP oracle calls more accurately than gene count alone?

## Sources and strict preregistration

- **Model:** BiGG iML1515, original frozen SBML SHA256 `9c772d44ca43350e40dc7ee86c7aa148796856be1eea45e5406c6df8f7dcde28`.
- **Training:** exactly 15 previously certified observations: five R9 sizes from [42239472392](https://github.com/Frane12/AndroidGameTest/actions/runs/42239472392) and ten R17 novel cohorts independently audited by [42344466528](https://github.com/Frane12/AndroidGameTest/actions/runs/42344466528).
- **Fresh prospective holdouts:** 336 previously unused gene IDs, comprising 192 SHA-ranked and 144 topology-ranked gene families. Both disjoint from each other and all **1,152** prior R9/R17 training genes. Each family tested at nested N = 24, 48, 96, 144 (the SHA family also at 192). **Nine cases**, two repetitions each.
- **Predictions and coefficient freeze first:** [R18 preregistration run 42346440066](https://github.com/Frane12/AndroidGameTest/actions/runs/42346440066), SHA256 `7faf2734f46dae13b285cd11ba248ad7e715ca809b37cdc896d7d8e58471a573`. This completed before any prospective solver jobs.
- **Prospective results and independent audit:** [run 42346553188](https://github.com/Frane12/AndroidGameTest/actions/runs/42346553188), status `PASS_FROZEN_PROSPECTIVE_AUDIT`, all **9/9 cohorts, 18/18 solver attempts completed**. Original frozen R9 algorithm, exact PySAT CaDiCaL + COBRA GLPK FBA, three SAT termination stages, independent verification of reported minimal knockout sets, 120-second cap. Original solver was not modified.
- **Wildtype flux pre-solve acquisition:** exactly **one additional GLPK LP solve**, measured **0.1099418 s**, and checked for metabolic mass balance and reaction bounds. **This is not total feature-extraction overhead:** graph and GPR feature-calculation CPU was not separately timed. When evaluating stand-alone deployment this additional LP and all graph/GPR preprocessing must be included; the original R9 solver also computes its own wildtype LP.
- **Models:** ridge regression with fixed λ = 2.0, trained only on the 15 original observations: (A) log(N), (B) log(N) + log(GPR graph pressure), (C) log(N) + log(GPR graph pressure) + log(wildtype flux-sensitive pressure). **Primary predeclared metric is RMS(log(predicted LP / observed LP))**; symmetric error applies to over- and underprediction. No post hoc retuning.

## Nine untouched forecasts versus observed LP oracle calls

| Gene family | N | Only N forecast | N + GPR forecast | N + GPR + wildtype flux forecast | Observed LP | Solver median (s) | Minimal sets |
|---|---:|---:|---:|---:|---:|---:|---:|
| New SHA | 24 | 9.891 | 1.597 | **2.264** | **5** | 0.229134 | 4 |
| New SHA | 48 | 25.242 | 5.135 | **7.046** | **9** | 0.331956 | 8 |
| New SHA | 96 | 64.419 | 16.637 | **26.045** | **25** | 0.917118 | 19 |
| New SHA | 144 | 111.435 | 33.156 | **48.603** | **49** | 1.999791 | 23 |
| New SHA | 192 | 164.397 | 54.112 | **80.430** | **79** | 3.550224 | 31 |
| New topology | 24 | 9.891 | 1.597 | **1.136** | **2** | 0.179175 | 1 |
| New topology | 48 | 25.242 | 5.135 | **7.046** | **9** | 0.328674 | 8 |
| New topology | 96 | 64.419 | 16.637 | **23.065** | **33** | 0.828897 | 12 |
| New topology | 144 | 111.435 | 33.156 | **45.935** | **55** | 1.592418 | 20 |

## Predeclared predictive metric and other error measures

| Model | RMS log error ↓ (primary) | Median symmetric multiplicative error ↓ | MAE, LP calls ↓ | MAPE ↓ |
|---|---:|---:|---:|---:|
| N only | 0.954628 | 2.274194× | 35.59702 | 1.60482 |
| N + GPR | 0.593383 | 1.658833× | 10.98191 | 0.400727 |
| **N + GPR + wildtype flux** | **0.369717** | **1.277334×** | **3.26442** | **0.216367** |

**Primary preregistered hypothesis supported** for this experiment: RMS log error of flux-aware model is lower than N-only. Flux-aware was closer than both baselines on 8 of 9 cases by absolute log error. The single new-SHA 24-gene test remains difficult (2.264 predicted vs 5 observed).

## Scientific interpretation and limitations

1. **Good positive predictive generalization to held-out gene identities on the same network**: source-only static GPR structure was weak in R17; adding a genuine wildtype primal metabolic-flux signal improved the predicted LP workload here under the symmetric predeclared metric.
2. **Not a complexity proof.** These are fixed-size k≤3 instances on a single metabolic network; observed time or LP-count scaling says nothing rigorous about worst-case NP-hardness or a general O(N^α) theorem.
3. **Not faster solving by itself.** This R18 experiment tests a forecaster ahead of an unchanged solver. Extra pre-solve flux/feature work incurs real cost and could slow an individual solve if no strategy change uses the forecast.
4. **Not independent biological datasets.** Nine nested cohorts share genes within family and all use one *E. coli* model. They are not nine independent organism tests; do not calculate naive significance as if independent.
5. **No external exhaustive proof of solution completeness for all R18 cohorts.** The original R9 SAT search ended in UNSAT for each exact-cardinality stage and each output minimal knockout set passed independent gene-vs-reaction FBA checks. This is different from independently running all possible gene-knockout combinations.
6. **Not native DRNAS, not cancer or drug efficacy.** This is the PySAT/COBRA research algorithm. No patient, cellular assay, therapeutic experiment or independent external-specialist comparison was run in R18.
7. The source model is frozen by SHA; R9/R17 source cases and R18 prospective gene sets and forecast files were pinned before heldout outcomes were available. The decisive evidence is the public run logs and downloadable original artifacts, not the narrative of this note.

**Reproducibility:** `research/drnas_medical/gmispy_r18_flux_forecast.py`; workflows `drnas-medical-r18-flux-forecast.yml` and `drnas-medical-r18-prospective.yml`.

### Next falsifiable test

Transfer the exact frozen flux-aware feature recipe and fixed training parameters to **another genome-scale metabolic model** with different biological structure, ensuring GPR parsing and objective normalization remain valid. Separately measure net cost if forecasts actively guide strategy choices, rather than merely predicting solver effort.
