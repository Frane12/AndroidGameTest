# DRNAS Medical gMISpy R1 — upstream regulatory-layer bridge

This branch is an **integration pilot**, not a validated biomedical result.

## Two intentionally separate tests

1. **Upstream gMISpy smoke**: install published `PlanesLab/cyclic-gMISpy` at immutable revision `76ce96de9d4e18c8200876f5a73d3b2d60e4a012`; import and invoke the actual `boolTransformer` and `bonesisCalculateCutSets` functions on a three-gene regulatory model. Preserve the exact result and elapsed time.
2. **DRNAS SAT audit**: three *synthetic*, gMISpy-style regulator/target Boolean networks with positive, negative and cyclic interactions, six genes each, AND/OR GPR viability rules, and 0–2 forced gene knockouts. Each of the 66 unique KO instances is independently and exhaustively checked on all 64 possible gene states, then translated to CNF and run using the same CNF under PySAT CaDiCaL and Kissat. The DRNAS R108 certified prepass is enabled on up to six selected instances; all preprocessing costs are included.

Each CNF, rule set, source SHA256, expected status, solver timing, and result is saved as a GitHub Actions artifact.

**Interpretation warning:** no empirical cancer data, no metabolic flux/MILP model, no demonstration that a knockout is therapeutically useful, and no direct timing comparison against the full gMISpy pipeline. The upstream smoke and DRNAS SAT test do not solve the same complete biomedical problem. The SAT pilot asks whether fixed points of the chosen abstract regulatory network allow a particular Boolean GPR marker. This does not reproduce gMISpy/BoNesis asynchronous-attractor and readjustment semantics.

## Next stage required for credible comparison

Freeze a publicly licensed metabolic model (SBML), regulatory network (CSV with source_ENSEMBL/target_ENSEMBL/interaction) and exact full-gMISpy outputs. Define a semantically equivalent SAT/PB feasibility subproblem in the real gMISpy workflow and compare same queries, limits and hardware to Gurobi/CPLEX/BoNesis baselines. Until equivalence is checked, no claimed DRNAS speedups vs gMISpy.

## Run

```bash
python3 -m pip install python-sat==1.9.dev18
python3 research/drnas_medical/gmispy_r1.py sat-benchmark --out medical-results/gmispy-r1 --cap 5 --r108 6
python3 -m pip install 'git+https://github.com/PlanesLab/cyclic-gMISpy.git@76ce96de9d4e18c8200876f5a73d3b2d60e4a012'
python3 research/drnas_medical/gmispy_r1.py upstream-smoke --out medical-results/gmispy-r1
```
