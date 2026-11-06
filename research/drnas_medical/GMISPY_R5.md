# DRNAS Medical R5 — 48-gene GPR master benchmark

## Experimental question

Does the R3/R4 structural SAT master retain its speed advantage when we expand the real *E. coli* gene knockout problem from **32 to 48 genes** and introduce a more biologically structured Gurobi MILP master?

The underlying real metabolic dataset is the published BiGG `e_coli_core` model, via frozen COBRApy 0.30.0 `textbook`. The SBML hash must be identical to certified R3/R4 `13daac1b0ef19a12459371d4c11d16122ffaccf207070c08a6a66f8ba983b91f`. All 95 reactions and their actual GPR AND/OR rules are reused unchanged.

The original R3 32 genes are frozen. An additional **16 genuine E. coli locus identifiers** (BiGG IDs matching `b[0-9]{4}`) participating in model reactions are selected deterministically by count of complex GPR reaction participation, then number of associated reactions, then gene ID. **The pseudogene `s0001`, which represents spontaneous reactions, is never a knockout target.** This may bias toward structural overlap, so conclusions must be restricted to this cohort; an externally held-out, randomly sampled group is still required.

There are **18,472 candidate sets of size 1–3**, each independently evaluated as both native COBRApy gene knockout and GPR-implied reaction knockout, for 36,944 LP FBA equivalence checks. Biomass loss is defined exactly as below 1% of simulated unperturbed maximum flux.

## Three algorithms / shared FBA

- `sat_structural_memo`: the R4 SAT master using PySAT CaDiCaL + monotone superset pruning + equivalent disabled-reaction signature caching.
- `gurobi_lazy_master`: the existing R4 Gurobi 12.0.3 mixed-integer binary gene master using MIPSOL callbacks, the same monotone cuts and identical GPR signature memoization.
- `gurobi_gpr_aware_mip`: a new Gurobi MIP master whose binary variables explicitly represent the true gene knockout choices AND the parsed GPR reaction-on/off Boolean relations. AND/OR are encoded using standard exact 0/1 MILP linearizations. It maximizes the number of disabled reactions only to direct **search order**; it still enumerates all candidates through sound lazy cuts and verifies biomass using the *same* GLPK oracle.

**All three are formulation benchmarks; none implements full gMISpy's cyclic Boolean network intervention analysis or an integrated single-shot dualized metabolic MIP.** The SAT core is **not native DRNAS**.

Run 2 interleaved repetitions with Gurobi single threaded. Each method must enumerate the identical inclusion-minimal KO set family (not merely the same count), or the experiment fails. Gurobi incomplete optimization must be explicitly labelled timeout, never assumed UNSAT. A separate audit compares each result to independently exhaustively certified FBA outcomes and confirms all 18 earlier R3/R4 minimal interventions still appear.

## Reproducibility

```bash
python3 -m pip install cobra==0.30.0 python-sat==1.9.dev21 gurobipy==12.0.3
python3 research/drnas_medical/gmispy_r5.py --out medical-results/r5 --extra-genes 16 --max-k 3 --repeats 2 --mip-cap 150
python3 research/drnas_medical/gmispy_r5_verify.py --summary medical-results/r5/summary.json --out medical-results/r5/verification.json
```

Workflow `.github/workflows/drnas-medical-gmispy-r5.yml`. Outputs: 18,472 gene/reaction KO audit rows, raw model SBML source, source hash, every candidate count, every LP call count and each individual wall time.

## Limitations

This is a **real bacterial metabolic simulation**, not a human tumor, clinical prediction or experimental drug-target result. It is not a native DRNAS SAT benchmark. The true full gMISpy may scale differently. Do not infer treatment relevance or broad solver superiority from synthetic intervention choices on one model.

**Scientific next step:** compare with the established original genetic minimal cut set MILP formulation, not merely two custom masters with lazy cuts, then test human Human-GEM or Recon3D models with properly sourced human regulatory interactions.
\n## Corrective audit note\n\nThe initial R5 run accidentally selected pseudo-gene `s0001` (BiGG representation of spontaneous reactions), producing non-biological intervention sets. That initial run and its observed times are retained for audit but are **not accepted as R5 scientific results**. The final R5 run excludes `s0001`, validates every selected gene against the `b[0-9]{4}` locus-ID pattern and reruns the independent 18,472-case audit and both MILP controls.\n