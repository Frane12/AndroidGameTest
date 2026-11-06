# DRNAS Medical R6 — original specialist gMCSpy defeats current SAT/LP prototype

**Date:** 6 Nov 2026.  
**Certified GitHub Actions run:** https://github.com/Frane12/AndroidGameTest/actions/runs/42223264995  
**Protocol:** [GMISPY_R6_PROTOCOL.md](GMISPY_R6_PROTOCOL.md)  
**Published competitor:** [PlanesLab/gMCSpy](https://github.com/PlanesLab/gMCSpy) at **`4567a6d14bd2e5517e7a86b17aebefb0f285544c`**, using `gMCSpy.calculateGeneMCS`, `geneSubset`, `maxKOLength=3`, Gurobi 12.0.3, single thread, published `staged-lazy` enumerator. This is the **published specialized gene-MCS implementation**, *not* full cyclic-regulatory gMISpy/BoNesis. We did not change its source implementation.

## Actual certified results

| Genuine E. coli locus gene cohort | Total possible KO sets (1–3) | Min. KO sets, exact | DRNAS-architecture SAT + GLPK median (3 reps) | Original gMCSpy G/F-matrix dual MILP median (3 reps) | Specialist advantage |
|---|---:|---:|---:|---:|---:|
| 48 genes, previously frozen R5 | 18,472 | 25 / 25 | **2.8258744 s** | **0.2227778 s** | **12.68x faster** |
| 64 genes, frozen 48 + 16 independently SHA-ranked extra genes | 43,744 | 70 / 70 | **7.9494851 s** | **0.3056364 s** | **26.01x faster** |

All outcomes validated against the exact, real gene knockout problem defined by this experiment, **not** simply comparing the number of returned results.

### Individual timings

**48 gene cohort**
- SAT architecture: `2.8042826`, `2.8258744`, `2.8546424` s
- Published gMCSpy: `0.2252586`, `0.2199088`, `0.2227778` s
- 25/25 identical inclusion-minimal gene KO sets, zero missing, zero extra, no incomplete enumeration warnings.

**64 gene cohort**
- SAT architecture: `7.9494851`, `7.9354197`, `7.9627817` s
- Published gMCSpy: `0.3059553`, `0.3041148`, `0.3056364` s
- 70/70 identical inclusion-minimal gene KO sets, zero missing, zero extra, no incomplete enumeration warnings.

All times are complete function wall times, excluding Python dependency installation. SAT arm includes its CaDiCaL CNF/cardinality enumeration and GLPK FBA on candidates; gMCSpy includes its original G/F extraction, dual MILP construction and solving. The original specialist **does not call an external LP separately per candidate**, which explains why the per-candidate SAT strategy is no longer competitive here.

## Independent frozen biological validation

- Same authentic `BiGG e_coli_core` (COBRApy textbook) source model SHA256:
  `13daac1b0ef19a12459371d4c11d16122ffaccf207070c08a6a66f8ba983b91f`.
- Model 95 reactions, 72 metabolites, 137 original gene entries. Intervention target sets are only actual `b[0-9]{4}` locus genes; pseudo-gene `s0001` was explicitly excluded.
- Phenotype: predicted maximal biomass flux after knockout **below 1% of wild-type** on fixed model medium.
- Independent full enumeration: 18,472 + 43,744 = **62,216** tested KO sets. Each was checked twice, through original COBRA gene-knockout operation and separately GPR-implied reaction knockout: **124,432 GLPK FBA checks**, all equivalent. The original gMCSpy's own numerical criterion yielded exactly the same minimal intervention sets on both tested cohorts.
- 48-gene cohort had 25 minimal sets (same as certified R5); 64-gene cohort had 70 minimal sets, including all the previous 25.
- SAT had 901 GLPK calls per run on 48 genes and 1,406 GLPK calls on 64 genes. Its memoization and monotone cuts reduce evaluations, but cannot match the specialist on this problem.
- Both cohort jobs and the independent crosscheck job finished `success`. Audit: `DRNAS_MEDICAL_R6_AUDIT`, `paired_gMCSpy_speed_claim_allowed=true`.
- Original solver revisions, exact input gene subsets, biological model hashes, per-repeat JSON, and detailed logs are preserved in the GitHub Actions artifacts.

## Scientific meaning

**Positive result:** Our SAT/LP prototype computes exactly correct genetic minimal intervention sets on two substantially larger real metabolic benchmarks and has safe structural/memoization reasoning.

**Negative performance result:** Against the actual specialist gMCSpy gene-MCS solver, the SAT/LP prototype is **12.68x–26.01x slower**. Earlier R4/R5 results claiming 3x–9x advantages applied *only to our own custom Gurobi candidate-enumeration masters*, not to gMCSpy, so they are **not competitive benchmark wins**.

**Why this is not general superiority of the other solver:** only one bacterial metabolic model, two overlapping gene subsets, limited three repeats, restricted to gene KOs of size at most 3. The 64 genes are an expanded cohort of 48, not a second independently curated organism. Our SAT engine is **PySAT CaDiCaL**, not native DRNAS. The published `gMCSpy` is a genuine specialist; the full `gMISpy` cyclic regulatory/Bonesis integration still has not been benchmarked on the same human tumor-related tasks. No clinical efficacy or therapy claims are supported.

## R7 experiment direction: eliminate LP-per-candidate calls

The winning method uses precomputed G/F matrices and a dual stoichiometric MILP, rather than a candidate-by-candidate FBA test. The next meaningful DRNAS experiment should:

1. Import **exactly the same gMCSpy G/F source matrices** after original preprocessing, or independently reproduce and prove every matrix row.
2. Build a SAT/PB/SMT or hybrid solver for the **dual minimal-cut constraints**, not the existing enumeration-plus-FBA oracle loop.
3. Check each candidate with the independent GLPK FBA oracle *only on final solutions*, checking UNSAT/certificates separately, while charging preprocessing plus all solve time.
4. Compare to the official published gMCSpy `staged-lazy` and `classic` modes, not an invented weak MIP.
5. Freeze genuinely unseen metabolic models/mediums and set same resource budgets. Include an independent human metabolic model *only with curated human GPR/regulatory data and distinct biomedical validation*.

Citable references:
- gMCSpy paper: https://doi.org/10.1093/bioinformatics/btae318
- gMISpy paper: https://pubmed.ncbi.nlm.nih.gov/41965071/
- Minimal cut set methodological review: https://pmc.ncbi.nlm.nih.gov/articles/PMC12014531/
