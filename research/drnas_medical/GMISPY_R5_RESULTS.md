# DRNAS Medical R5 — corrected, audited final results (2026-11-06)

**Certified successful workflow:** https://github.com/Frane12/AndroidGameTest/actions/runs/42221663351  
**Version:** `experiment/drnas-medical-gmispy-r5-gpr-mip-20261106` (`99ad61154f2e7e306a4a4bd103f4aee364d26149` at benchmark run).

## Biological data integrity

- Real `BiGG e_coli_core` model, same source SHA-256 across R2–R5: `13daac1b0ef19a12459371d4c11d16122ffaccf207070c08a6a66f8ba983b91f`.
- 95 metabolic reactions, 72 metabolites, 137 model gene entries. Intervention candidates: **48 actual E. coli b-numbered locus gene IDs** (all match `b[0-9]{4}`). Includes the 32 fixed from R3/R4 + 16 additional GPR-related genes. Spontaneous `s0001` must not be a target.
- **18,472** candidate knockout subsets (1, 2, 3 genes) checked independently with *both* native gene KO and Boolean GPR-derived reaction KO, **36,944 reference GLPK LP calls**. The source gene/reaction knockout equality and monotonicity tests passed throughout.
- Final minimal intervention count: **25**, including all **18** earlier R3/R4 minimal sets. This is growth disruption in a fixed bacterial model only, defined at less than 1% of model wild-type biomass.

### Critical data-cleaning correction

Initial run `42220974017` included pseudo-gene `s0001` (associated in BiGG with spontaneous reactions), and the original log reported 41 minimum sets. **Those numbers are INVALID for genuine gene perturbations and are superseded by this corrected run.** The final workflow's audit now fails closed if any KO target is not a `b[0-9]{4}` E. coli locus gene ID. The corrected final run has **25** minimal sets; not 41.

## Actual measured algorithm timings — 2 paired repetitions

Three algorithms use identical selected 48 genes, same 18,472 independent reference comparisons, same GLPK FBA oracle, exact minimal-set semantics, the same positive AND/OR GPR biological rules, same monotone blocking and reaction-signature caching (so LP work is equal).

| Method | Run 0 (s) | Run 1 (s) | Median (s) | Ratio vs SAT |
| --- | ---: | ---: | ---: | ---: |
| DRNAS-architecture SAT CaDiCaL + GPR memo | 2.1948307 | 2.1813222 | **2.18807645** | **1.00x** |
| Gurobi 12.0.3 generic lazy MIP master | 18.4056686 | 16.2739739 | **17.33982125** | **7.92x slower** |
| Gurobi 12.0.3 GPR-aware AND/OR MIP master | 19.5335456 | 18.9516627 | **19.24260415** | **8.79x slower** |

All three:
- Evaluated **11,036** unique candidate subsets per repetition;
- Used only **901 GLPK LP oracle calls** thanks to exact reaction-signature caching;
- Reused **10,135** previous metabolically equivalent results;
- Recovered the same **25 inclusion-minimal gene KO sets** and passed independent exhaustive verification.
- Relative to 18,472 naive uncached candidate LP checks, both optimized algorithms save 95.12% of candidate LP calls. This pruning/cache gain applies to **all** three methods and should not be claimed as exclusive to SAT.

## Seven new minimal gene knockout sets compared with R3/R4

- `b2417 + b1819`
- `b0115 + b0904 + b2492`
- `b0114 + b0904 + b2492`
- `b0116 + b0904 + b2492`
- `b0118 + b1276`
- `b2416`
- `b2465 + b2935`

The first 18 remain precisely those verified in R3/R4. These are **in silico bacterial gene deletion hypotheses**, not experimentally verified growth effects or medical treatment claims.

## What was and was not demonstrated

**Demonstrated:** The combination of a SAT cardinality master and shared monotone cuts plus a biological GPR-signature memo makes the **enumeration master** substantially faster than **two custom Gurobi MIP masters** on the same exact reference E. coli knockout task. Same biological query, identical oracle and source hash, all 25 exact matches.

**Not demonstrated:** This is not the compiled native DRNAS solver (SAT engine = PySAT CaDiCaL), not the full gMISpy solver including Gurobi/BoNesis genetic network reprogramming, not an optimized integrated stoichiometric MILP (the GPR-aware model embeds gene–reaction logic but calls GLPK externally). No cancer, drug efficacy, patient data or experimental biological validity claim is warranted. Only **two** paired repeats, and the extra gene selection prioritized complex GPRs; generalization requires more blinded model families and stronger references.

## Independent certificate

`DRNAS_MEDICAL_R5_CERTIFIED_CROSSCHECK: PASS` established:
- 48 valid real E. coli locus KO candidates, no spontaneous pseudo-gene.
- 18,472 independent combos, 36,944 matched gene/reaction growth evaluations.
- All 25 minimal gene KO sets and all 18 frozen earlier R3/R4 reference sets.
- Every paired algorithm ran to full completion.
- Source SBML SHA unchanged from R3/R4.

GitHub Actions artifacts: `drnas-medical-r5-benchmarks` (full SBML, CSV, JSON and timings) and `drnas-medical-r5-proof` (independent verification JSON).

## R6 rigorous follow-up

Introduce the specialized published gMISpy gene minimal intervention MILP, freeze identical constraints and target phenotype, plus a larger blind holdout model and 5+ repetitions. For medicine, Human-GEM/Recon3D with curated human cancer-relevant regulatory data; predictions are only computational until biologically validated.
