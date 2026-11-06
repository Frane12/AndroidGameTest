# DRNAS Medical R6 — *published* gMCSpy genetic minimal cut set benchmark

## Why R6 is a stronger comparison

R4/R5 demonstrated advantages against specific, experimental Gurobi binary gene-KO search masters. Those were **not** gMCSpy's sophisticated original formulation.

R6 directly invokes **the published original `gMCSpy.calculateGeneMCS`** with `geneSubset`, `maxKOLength=3`, `enumeration="staged-lazy"`, Gurobi and a single thread. This is a genuine gene-MCS G/F-matrix dual MILP algorithm, not a hand-written generic master. Source pinned to `PlanesLab/gMCSpy@4567a6d14bd2e5517e7a86b17aebefb0f285544c` (2026-08-21). This is **gMCSpy** (genetic minimal cut set specialist), not the full **gMISpy** integrating cyclic regulatory BoNesis logic.

The paired control is the R5 DRNAS-architecture SAT master (PySAT CaDiCaL + safe superset cuts + memoization of exact disabled-reaction signatures + independent GLPK FBA). Neither arm runs the native compiled DRNAS SAT solver.

## Frozen realistic biological problem

- Model: published BiGG `e_coli_core` as COBRApy `textbook`, same fixed medium and biomass objective.
- Raw source SBML digest **must** match frozen R2–R5: `13daac1b0ef19a12459371d4c11d16122ffaccf207070c08a6a66f8ba983b91f`.
- Cohort A: 48 genuine `b[0-9]{4}` genes (R5 verified, excludes pseudo-gene `s0001`). Exactly `C(48,1)+C(48,2)+C(48,3)=18,472` intervention sets.
- Cohort B: extend cohort A with 16 previously unused gene IDs, using fixed SHA256 ranking of ID and a precommitted text seed, rather than choosing genes by solver runtimes. Exactly `C(64,1)+C(64,2)+C(64,3)=43,744` intervention sets. This is a **holdout extension**, not a completely independent model family.
- Phenotype: no more than 1% of the original model biomass flux under the same environment. The published solver can have a different numerical tolerance or exact definition of blocked biomass; **a speedup is only publishable here if its entire returned gene-cut family agrees exactly with the reference**.
- Reference: independent exhaustive COBRApy gene knockout FBA **and** separate GPR-derived reaction knockout FBA for every candidate. Exactly twice as many GLPK checks as enumerated gene sets.
- 3 repeated, alternating-order trials per solver per cohort on the same runner, each original specialist capped at 120 s plus a separate subprocess launch/install-independent outer watchdog. Count total wall including original `calculateGeneMCS` G/F preprocessing/optimization and SAT preprocessing/candidate/oracle work. Raw installation time is excluded from both.

## Verification requirements

The audit independently checks:
- All gene IDs correspond to genuine locus genes, not `s0001`.
- Model SHA, group selection, source and run outputs are frozen.
- All candidate genes are within the frozen set and max 3 KOs.
- Every returned gMCSpy intervention must belong to the independently verified minimal set.
- Original gMCSpy must return **all** independently validated minimal sets, with no duplicates or incomplete-enumeration warnings, before a speed ratio can be shown.
- **If gMCSpy times out or its solver semantics differ from the 1%-biomass endpoint, no direct speedup over the original is established.** These are reported as incomplete or incompatible, not assigned PAR-2 wins.

## Caveats

Not native DRNAS vs gMCSpy comparison; the SAT engine is CaDiCaL. Not the entire 2026 gMISpy cyclic regulatory algorithm; it does not use Human-GEM, DepMap, or patient data. This is a bacterial model, not validated cancer therapeutic predictions. Even an observed factor of improvement in one fixed cohort requires additional models, fixed budgets, genuine unseen datasets, and stronger optimized implementations for a competitive claim.

### Reproduce

```bash
python3 -m pip install cobra==0.30.0 python-sat==1.9.dev21 gurobipy==12.0.3 beartype joblib bidict scipy tqdm
python3 -m pip install --no-deps 'git+https://github.com/PlanesLab/gMCSpy.git@4567a6d14bd2e5517e7a86b17aebefb0f285544c'
python3 research/drnas_medical/gmispy_r6_specialist.py benchmark --out medical-results/r6-48 --cohort 48 --max-k 3 --repeats 3 --competitor-cap 120
python3 research/drnas_medical/gmispy_r6_specialist.py benchmark --out medical-results/r6-64 --cohort 64 --max-k 3 --repeats 3 --competitor-cap 120
python3 research/drnas_medical/gmispy_r6_verify.py --cohort48 medical-results/r6-48/summary.json --cohort64 medical-results/r6-64/summary.json --out medical-results/r6-certified.json
```

Original sources: [gMCSpy](https://github.com/PlanesLab/gMCSpy), [gMISpy](https://github.com/PlanesLab/cyclic-gMISpy), [BiGG e_coli_core](https://bigg.bio/models/e_coli_core/), [MCS scientific review](https://pmc.ncbi.nlm.nih.gov/articles/PMC12014531/).
