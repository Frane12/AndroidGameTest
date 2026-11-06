# DRNAS Medical R3 — measured results (6 November 2026)

**All three GitHub Actions jobs passed:** https://github.com/Frane12/AndroidGameTest/actions/runs/42216131752

Source: real `BiGG e_coli_core`, 95 reactions, 72 metabolites, 137 genes, 32 selected for interference; COBRApy 0.30.0, `textbook` model. Exact SBML SHA256: `13daac1b0ef19a12459371d4c11d16122ffaccf207070c08a6a66f8ba983b91f`.

The input contains **15 GPR reaction rules containing AND** and **32 containing OR**. Enzyme complexes, shared genes, and alternate isoenzymes were represented using original real gene-protein-reaction relationships. These are **not** tumor models or added human regulatory interactions.

## Externally reproducible source-constrained experiment

Independent exhaustive GLPK FBA analysis evaluated all 5,488 gene knockout sets of size 1–3, and for **every** such gene set separately verified that knocking out the Boolean GPR-implied reactions produced the same biomass. This took 10,976 LP calls. A gene KO was declared biomass-disrupting if modeled optimum biomass fell below 1% of wild-type value.

Three SAT + GLPK algorithms used exactly the same underlying model, PySAT CaDiCaL 1.9.5 candidate generator, and 3 repetitions with rotated order. Times are full wall times in seconds including structural GPR work and LP calls (not just SAT).

| Method | Candidates per repetition | LP calls per repetition | Median full wall (3 repeats) | Speedup against plain |
| --- | ---: | ---: | ---: | ---: |
| Plain SAT + GLPK | 5,488 | 5,488 | 2.9354787 | 1.00x |
| Structural minimal-set superset exclusion + GLPK | 2,730 | 2,730 | 1.1108879 | 2.6425x |
| Structural superset exclusion + GPR reaction-signature memo + GLPK | 2,730 | 716 | 0.6196443 | 4.7374x |

- Structural pruning reduced **LP calls by 50.26%** relative to plain (5,488 to 2,730).
- Added GPR signature memo reduced **LP calls by 86.95%** relative to plain (5,488 to 716) with **2,014 exact reaction-signature cache hits**.
- All three arms identified the **same 18 inclusion-minimal gene KO sets** and agreed with the independent exhaustive FBA oracle.
- The original gMISpy's actual `getGPRDict` and `boolTransformer` on the same model were compared with our interpretation of six complex GPR rules by independently evaluating **804 truth-table assignments**; all agreed. Source SHA was identical.
- Independent GitHub crosscheck job: `DRNAS_GMISPY_R3_CROSSCHECK: PASS`.

## Confirmed 18 minimal gene knockout sets

Singles (6):
`b2926`, `b1779`, `b2779`, `b1136`, `b0720`, `b2415`.

Pairs (10):
`b3919+b0767`, `b3919+b1852`, `b3919+b2029`, `b3919+b4025`, `b3236+b3956`,
`b0767+b4025`, `b1852+b4025`, `b2029+b4025`, `b1818+b2417`, `b1817+b2417`.

Triples (2):
`b3919+b3236+b0474`, `b3919+b3236+b1702`.

**Interpretation:** these are only combinatorial deletions predicted to suppress bacterial growth in a particular in silico medium. They are not therapeutic targets, validated genetic interventions in a laboratory, or confirmed cancer biology.

## Limits and integrity

The R3 SAT engine is **CaDiCaL via PySAT**, with novel DRNAS-inspired pruning and GPR-signature memoization; it is **not** a native DRNAS solver speed test. The original gMISpy's full Gurobi/Bonesis mixed metabolic/regulatory algorithm was **not** run on these exact gene knockout problems; only its original GPR parsing helpers were called and independently verified. Consequently the measured 4.74x is **versus an unoptimized SAT+LP control built for this experiment**, not versus gMISpy, Kissat, an optimized MILP, or world-leading biomedical solvers.

Three runs of roughly 0.6–3 s on a single GitHub runner do not guarantee transfer to larger, real-world human metabolic networks. Sources and outputs are stored in GitHub Actions artifacts:
`drnas-gmispy-r3-complex-sat-fba`, `drnas-gmispy-r3-original-gpr`, `drnas-gmispy-r3-verified-crosscheck`.

## Next fair experiment

To establish an externally meaningful advance, implement comparable **gene-based** knockout constraints in a strong, published MIP/PB solver on the **same** GPR/FBA problem, with same media, candidates, 1–3 gene cap, output definition and timing budget. Then scale to human metabolic Recon3D or Human-GEM and organism-matched gene regulation with frozen, curated evidence.
