# DRNAS Medical R2 — real metabolic intervention pilot (2026-11-06)

## Exactly what is real, and what is not

- Uses actual published *E. coli* K-12 core genome-scale metabolic reconstruction (BiGG `e_coli_core`, 95 reactions / 72 metabolites / 137 genes), bundled as `cobra.io.load_model("textbook")` in COBRApy 0.30.0.
- Intervention target is **loss of modeled biomass flux** below 1% of wild-type optimum in fixed medium. This is mathematical growth suppression in a constraint-based bacterial model, **not cancer treatment**.
- Selects at most 18 reproducibly ordered gene-reaction pairs with a strictly one-to-one gene relationship and exact single-gene GPR rule. Thus gene KO and reaction KO should be functionally equivalent; verify *each* candidate by independently performing both knockout variants with COBRApy + GLPK. Fail closed on any discrepancy.
- Exhaustively enumerates all single and double interventions in this selected subset and compares the minimal growth-blocking sets to a SAT candidate generator (PySAT CaDiCaL 1.9.5 + cardinality network + GPR structural monotone nogood) using the same GLPK FBA growth oracle.
- The same exact selected reaction subset is fed to the **real** upstream `cyclic_gmispy.calculateMCS` (Gurobi MILP backend), pinned to `PlanesLab/cyclic-gMISpy@76ce96de9d4e18c8200876f5a73d3b2d60e4a012`. Each returned original MCS solution is independently rechecked on the actual model. A licensing or API error is recorded as a failure, not treated as a result.
- Persist raw SBML as an Actions artifact with SHA-256 digest, objective, knockout selection, per-instance LP status, wall times, all minimal solutions, algorithmic decisions, original gMISpy MCS result/error.

## What this is not

- No human/animal drug effectiveness conclusions.
- No real OmniPath/SIGNOR/DoRothEA regulatory feedback in the E. coli network. They are human regulator databases, and copying their interactions to bacteria would be scientifically invalid.
- No validated equivalence to full cyclic gMISpy's marker reprogramming or cellular readjustment models: that requires real organism-matched regulatory source and matching transition semantics.
- No claim of native DRNAS SAT superiority: the SAT master is a CaDiCaL-wrapped research implementation that uses DRNAS's proposed monotonic structural cuts; LP dominates many timings. The original upstream method is mixed-integer reaction-based minimal cut set search, so the timing comparison is contextual unless outputs and feasible sets are independently verified. The exhaustive baseline makes twice as many GLPK calls per candidate to verify exact KO equivalence.
- No repeated or blinded time measurements yet: the purpose of R2 is correctness and meaningful real biological model integration, then R3 can enlarge and blind-test.

## Source references

- BiGG Models `e_coli_core`: https://bigg.bio/models/e_coli_core/
- Model scientific resource: https://doi.org/10.1093/nar/gkv1049
- Official upstream gMISpy source: https://github.com/PlanesLab/cyclic-gMISpy
- Source workflow: `.github/workflows/drnas-medical-gmispy-r2.yml`

## Reproduce

```bash
python3 -m pip install cobra==0.30.0 python-sat==1.9.dev21
python3 research/drnas_medical/gmispy_r2.py sat-lp --out medical-results/r2 --max-genes 18 --growth-ratio 0.01

python3 -m pip install 'git+https://github.com/PlanesLab/cyclic-gMISpy.git@76ce96de9d4e18c8200876f5a73d3b2d60e4a012'
python3 research/drnas_medical/gmispy_r2.py upstream-mcs --out medical-results/r2-upstream --max-genes 18 --growth-ratio 0.01
```
