# DRNAS Medical R17 — Certified Prospective Pre-solve LP Forecast Audit

**Recorded:** 2026-11-07  
**Scope:** genome-scale BiGG iML1515 (1,516 genes, 2,712 reactions, 1,877 metabolites); max 3 gene knockouts. This is the PySAT CaDiCaL/COBRA GLPK research engine, not native compiled DRNAS and not a human tumor model.

## Research question

Can GPR and gene-reaction structure available **before** SAT/LP candidate solving predict the actual number of FBA linear programming (LP) calls more accurately than the number of candidate target genes alone?

Prediction is different from explanation. An excellent post hoc regression of execution time against observed LP calls is **not** a pre-solve prediction when LP count is unknown until completion.

## Pre-registration and independence

- **Frozen source SBML SHA256:** `9c772d44ca43350e40dc7ee86c7aa148796856be1eea45e5406c6df8f7dcde28`.
- Training from independently audited R9 [run 42239472392](https://github.com/Frane12/AndroidGameTest/actions/runs/42239472392), with recorded original target sizes N = 24, 48, 96, 192 and 384, and LP counts 26, 83, 82, 243, 1070.
- Primary predeclared model: ridge regression on log(N) and log(1 + gene–reaction graph pressure), λ=0.75.
- Primary control: N-only log–log power model. Secondary model: graph-pressure-only power model.
- Two *disjoint* prospective target-gene families, each nested at N = 24, 48, 96, 192, 384, selected from genes **absent from the original R9 384-gene pool** by fixed SHA ranking and source-model degree, not by measured knockout phenotype, LP counts or SAT timings.
- **The SHA-256 of the predictions was frozen before any prospective solver runs:** `f4af4391321af37d8faa26097b26182d97090a83252c21c14f8d63366ff946dd`.
- 10 prospective cases × 2 repetitions, exact original R9 algorithm, 120-second in-solver cap, independent gene vs reaction FBA validation for returned minimal cuts, and three stages ending in SAT UNSAT.
- Original [R17 prospective action](https://github.com/Frane12/AndroidGameTest/actions/runs/42344188975) completed all 10 × 2 solver trials. Its *final audit job alone* failed because NumPy was missing. Separate [immutable-artifact audit run 42344466528](https://github.com/Frane12/AndroidGameTest/actions/runs/42344466528) recovered all **unchanged** artifacts, independently verified the freeze SHA and passed `R17_FINAL`. **No retraining** or post-selection of predictors occurred.
- This is a prospective test on new gene groups of **one organism**, not unseen organisms or patient data.

## Individual original forecasts and actual measured LP calls

| Family | Genes N | N-only forecast | N + GPR structural forecast | Actual LP calls | Median solver time (s) | Minimal cut sets |
|---|---:|---:|---:|---:|---:|---:|
| SHA-selected | 24 | 24.746 | 0.002 | **2** | 0.210840 | 1 |
| SHA-selected | 48 | 57.948 | 0.034 | **6** | 0.271383 | 4 |
| SHA-selected | 96 | 135.697 | 0.326 | **16** | 0.530984 | 10 |
| SHA-selected | 192 | 317.765 | 3.413 | **44** | 1.675721 | 21 |
| SHA-selected | 384 | 744.116 | 36.734 | **395** | 18.238956 | 52 |
| Degree-selected | 24 | 24.746 | 0.183 | **15** | 0.544107 | 7 |
| Degree-selected | 48 | 57.948 | 1.046 | **30** | 0.619365 | 9 |
| Degree-selected | 96 | 135.697 | 5.521 | **60** | 2.104163 | 12 |
| Degree-selected | 192 | 317.765 | 22.364 | **334** | 12.855854 | 30 |
| Degree-selected | 384 | 744.116 | 82.970 | **986** | 37.046774 | 55 |

**All 10 cases completed**, were internally repeatable across both attempts and had their returned minimal intervention solutions independently checked. Two categories at each size belong to separately selected, disjoint gene families; the genome-scale metabolic model itself is the same.

## Predeclared metric and why it is inadequate alone

Original audit **MAPE**, defined as mean |predicted/actual − 1|:

| Model | MAPE | MAE (LP calls) |
|---|---:|---:|
| N-only | 377.55% | **118.88** |
| Graph-only | 99.73% | 187.26 |
| N + graph ridge | **95.12%** | 173.54 |

The audit output marks the primary as winning by **MAPE**. This alone is **misleading** for strictly positive counts because underpredicting all observations by almost 100% incurs MAPE ≈100%, whereas overprediction can incur arbitrarily high MAPE. It is especially misleading here because the graph model forecast physically impossible counts below **one** in some cases.

## Symmetric multiplicative out-of-sample error

Use the model-independent and symmetric factor for each case:
```
absolute_log_error = abs(log(predicted_LP / observed_LP))
multiplicative_error_factor = exp(absolute_log_error)
```
Report exp(median absolute log error) for 10 cases; 1× is perfect, 2× means a factor-of-two discrepancy whether too high or too low.

| Model | Median multiplicative error | Geometric mean multiplicative error | RMS log error |
|---|---:|---:|---:|
| **N-only** | **2.09×** | **3.27×** | **1.476** |
| **N + graph** | **20.70×** | **37.45×** | **3.893** |

These metrics were chosen for explanatory analysis *after* inspecting the outcome and should be labeled **post hoc secondary diagnostics**. The primal, frozen forecasts themselves were unchanged.

## Conclusions

1. The predeclared GPR structural predictor does **not** generalize satisfactorily to prospective disjoint gene cohorts; on a symmetric scale it performs **much worse than N alone**. This is a negative but scientifically useful result.
2. Gene count alone is insufficient to accurately predict LP oracle calls. At N=384 the two *different* gene families on the *same* iML1515 network required 395 and 986 LP calls (2.50× apart) and ran in 18.24 and 37.05 seconds. Network and phenotype-dependent structure matter, but the simple static graph proxy is not sufficient.
3. Successful solver completion, exact SAT search termination, and biological verification are **separate** from success of the forecast model. A failed mathematical predictor does **not** imply poor solving performance.
4. **Neither** these observations nor the earlier R9 log–log slope prove a general O(n^α) upper bound, nor a breakthrough in NP-hard general complexity.
5. A defensible next study is to preregister an improved hypothesis using (a) wild-type feasible flux support and the set of gene knockouts that can *actually* invalidate it, (b) topology of shared reaction supports and GPR minimal cut candidates, and (c) training on multiple source networks. Predictions must again be frozen before genuinely unseen target families/organisms are solved.
6. Purely static GPR topology is zero-extra-LP to compute; wild-type flux support requires an LP solve and its time must be charged as feature-acquisition overhead. Do not make it seem free.

**Evidence:** original [R9](https://github.com/Frane12/AndroidGameTest/actions/runs/42239472392), [R17 preregistration and prospective trials](https://github.com/Frane12/AndroidGameTest/actions/runs/42344188975), [R17 recovery audit](https://github.com/Frane12/AndroidGameTest/actions/runs/42344466528), source `research/drnas_medical/gmispy_r17_structural_forecast.py`.
