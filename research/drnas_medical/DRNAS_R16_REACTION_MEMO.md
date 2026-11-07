# DRNAS Medical R16 — exact GPR reaction-signature FBA memoization

## Research question

DRNAS Medical R15 revealed that the **k = 3 stage** accounts for roughly 81% of the total work in one 384-gene gated-fresh trial: 33.375 of 41.249 s, and 878 of 1,107 LP requests. R15 also found conditional speedups from keeping a CaDiCaL solver between stages 1 and 2, but a regression at 96 genes.

We are testing whether repeating the *same metabolic LP state* for **different knockout gene subsets** explains some of the cost. If two gene subsets map under the **complete published GPR rules** to the **exact same disabled reaction IDs**, their LP feasible regions have identical reaction constraints and biomass objective in a single frozen iML1515 model.

We explicitly do NOT assume that equal gene-set size, equal number of disabled reactions, or similarity of reaction sets is sufficient. Only exact full signatures qualify for reuse.

## Precommitted arms

- `r9_baseline`: original R9 three independent CaDiCaL stages, no memo.
- `share_12_control`: original R15 sharing solver only across cardinality k = 1 and k = 2, no memo.
- `share_12_memo_k3`: same R15 solver lifetime, exact reaction-signature FBA cache only within stage k = 3.
- `share_12_memo_all`: exact signature reuse across all three stages and same solver lifetime.
- `gated_fresh_memo_k3`: R14 gated fresh CaDiCaL each stage, with exact k = 3 memo to separate cache from cross-stage solver-lifetime benefit.

## Validation

Every cache miss invokes the original `r9.certified_flux`, including stoichiometric balance and disabled-reaction checks for viable flux witnesses. An exact signature hit reuses the same certified flux and objective. Predetermined hit numbers (1, 2, 8, 32, 128, 512) are re-evaluated with the original LP routine and checked for identical phenotype and objective within 1e-6.

All final reported minimal knockout sets must:
- match the exact frozen R10 reference set;
- independently pass R9's gene-KO vs reaction-KO FBA verification;
- finish all three k stages;
- report full original CNF/biological model source SHA and the original LP request count;
- report *actual physical LP solves*, distinct from LP **requests**, including verification rechecks as charged work.

This remains a bacterial *E. coli* iML1515 test, **not a human cancer model**, and uses Python/PySAT CaDiCaL/COBRA/GLPK — not native DRNAS SAT. Completeness is independently exhaustively verified only for 24 and 48 genes. Larger groups rely on algorithmic SAT exhaustion and independent validation of returned minimal sets.

## Experimental matrix and interpretation

5 frozen nested gene cohorts: 24, 48, 96, 192, 384.
5 arms per cohort, 3 deterministic repetitions, same R9/R10 source and biological reference: 75 total trials.
Every original R9 trial has a 150-second algorithmic cap.

Primary measures: stage k3 wall time, actual LP solves saved (not merely cache hits), total wall time and paired speedup vs `share_12_control`, SAT and LP call counts, correct interventions, number of reaction-signature collisions and direct LP rechecks.

Cache *overhead may exceed savings* for subsets where many candidates disable distinct reaction sets. A zero-hit cache must not be called an improvement. Improvements in the controlled source are **not an independent blind validation**.

GitHub Actions: https://github.com/Frane12/AndroidGameTest/actions/runs/42342220263

Code: `research/drnas_medical/gmispy_r16_reaction_memo.py`
Workflow: `.github/workflows/drnas-medical-r16-reaction-memo.yml`
