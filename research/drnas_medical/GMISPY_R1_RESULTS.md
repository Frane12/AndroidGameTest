# DRNAS Medical gMISpy R1 — verified CI results (2026-11-06)

- Successful run: https://github.com/Frane12/AndroidGameTest/actions/runs/42211848017
- Revision tested: `2014400a640f6e8c683f41afba83b8e6492a66a7`
- Workflow: `.github/workflows/drnas-medical-gmispy-r1.yml`
- Artifacts: `drnas-gmispy-r1-sat-audit`, `drnas-gmispy-r1-upstream`
- **Scope**: synthetic Boolean fixed-point network knockout queries and a *separate* upstream gMISpy regulatory-layer smoke test. Not real cancer data and NOT a full gMISpy benchmark.

## Fully validated Boolean feasibility experiment

Three synthetic six-gene networks, 22 intervention subsets each (zero, one, or two knockout genes). A brute-force independent 2^6-state oracle checked each instance.

| Method | Trials | SAT | UNSAT | Time (wall, s) |
|---|---:|---:|---:|---:|
| CaDiCaL 1.9.5 via PySAT | 66 | 24 | 42 | 4.505853 |
| Kissat 4.0.4 via PySAT | 66 | 24 | 42 | 4.478390 |
| DRNAS R108 + CaDiCaL | 6 | 5 | 1 | 0.740385 |

On the *same six* cases selected for R108, plain CaDiCaL took 0.434356 s and R108+CaDiCaL took 0.740385 s. The paired aggregate slowdown is 1.70456x (DRNAS time / baseline time). R108 preprocessing alone consumed 0.333122 s. These are tiny CI process-wall measurements, not representative larger-scale SAT throughput.

The no-viable-fixed-point knockout sets (only counting models that retain at least one fixed point) found:
- feedback: minimum 1, C or F;
- inhibitory: minimum 1, D or F;
- mixed: minimum 2, B+E, B+F or D+F.

All 66 CNFs and 138 timing records are available in the artifact. No timeouts reported.

## Real upstream gMISpy smoke

The upstream `PlanesLab/cyclic-gMISpy` source was installed from immutable commit `76ce96de9d4e18c8200876f5a73d3b2d60e4a012` and its **actual** `boolTransformer` and `bonesisCalculateCutSets` routines succeeded. Input was a tiny synthetic chain `A -> B -> C` with marker `gpr=C`; gMISpy reported `gpr=0`, `A=0`, `B=0`, `C=0` solutions in 0.035060094 s (function call only; dependency installation excluded).

**These two jobs do not implement equivalent full metabolic models and cannot support a speedup claim over gMISpy.**

## Next honest research milestone

Choose and freeze a small real published SBML metabolic model + explicit regulatory CSV, reproduce the original gMISpy pipeline with BoNesis and MIP, derive proof-checked SAT/PB queries for the *same* intervention semantics, and then carry out paired trials with frozen sources and blind holdout.
