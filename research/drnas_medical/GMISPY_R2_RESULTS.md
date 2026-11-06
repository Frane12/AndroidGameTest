# DRNAS Medical R2 — verified real metabolic results (2026-11-06)

**Run:** https://github.com/Frane12/AndroidGameTest/actions/runs/42213146250  
**R2 scientific scope:** BiGG E. coli core metabolism, not human cancer, no external regulatory edges.  
**Source:** COBRApy 0.30.0 bundled `textbook` / published BiGG `e_coli_core` with 95 reactions, 72 metabolites and 137 genes. Frozen output SBML SHA256: `13daac1b0ef19a12459371d4c11d16122ffaccf207070c08a6a66f8ba983b91f`.

- Wild-type biomass optimum: `0.8739215069684279`.
- Knockout defined as stopping modeled biomass below 1% of wild-type (`0.008739215069684279`), on a fixed medium.
- 18 selected, exact one-gene/one-reaction GPR pairs, in a reproducible order.
- Exactly 171 gene knockout combinations tested (18 singles + 153 doubles).
- Independent exhaustive reference: 342 metabolic GLPK LP evaluations, each gene knockout paired with the exactly matching reaction knockout. Wall = 0.086804855 s.
- Proposed DRNAS SAT-LP (CaDiCaL candidate generator + sound no-superset structural blocking + GLPK): 96 LP calls, 98 SAT calls, 0.001403983 s solver time, total wall 0.027252894 s.
- Original published gMISpy `calculateMCS` (Gurobi): 13 solution sets, runtime of actual optimization call 0.07801 s, rechecked on the identical biological model. Gurobi nonproduction restricted license was available in the run.
- **Exact set match**: All 13 minimum 1- or 2-gene sets were identical between independent exhaustive FBA, our SAT-LP and original upstream gMISpy MCS. Manual comparison of both GitHub Action artifacts confirmed this (not merely matching counts).
- **Pruning**: 171 enumerated combinations vs 96 LP-tested by DRNAS, reduction of 75/171 = 43.86% candidate evaluations. Reference deliberately includes two LP calls per candidate to validate equivalence, so its wall clock cannot be used as a clean speed comparison.
- **Not a DRNAS native solver breakthrough**: the prototype SAT core is PySAT CaDiCaL, with model-specific monotone clauses proposed by DRNAS, plus GLPK FBA. Original gMISpy is a different MILP algorithm. Three elapsed times are single-run, very small and not a repeated statistically controlled benchmark; do not quote 0.027/0.078 as proven speedup. No evidence about real tumor control or gene-target treatment.

## 13 exact matched minimal gene intervention sets

Singletons: `b0720`, `b1136`, `b1779`, `b2779`, `b2926`.

Pairs: `b0767 + b4025`, `b1852 + b4025`, `b2029 + b4025`, `b3236 + b3956`, `b3919 + b0767`, `b3919 + b1852`, `b3919 + b2029`, `b3919 + b4025`.

## Next research step

1. Verify output equality via separate automated GitHub Actions third job (new R2 validation run).
2. Add repeated, interleaved same-CI-run timing with equal FBA-audit accounting to separate SAT search overhead from oracle cost.
3. Expand from 18 chosen single-enzyme reactions to real complex GPR AND/OR rules, increasing difficulty without losing exact gene/flux semantics.
4. Only then add **real organism-matched regulatory relationships**, and test BoNesis/MPBN intervention constraints; do not imply this R2 test already models full cyclic gMISpy.
5. For cancer-specific applications freeze human metabolic + human gene-regulatory networks, with lineage and independent validation.

The R2 outputs can be downloaded from the attached GitHub Actions artifacts `drnas-gmispy-r2-real-metabolic-audit` and `drnas-gmispy-r2-original-MCS`.
