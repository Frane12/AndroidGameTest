# DRNAS Medical R3 — real complex GPR SAT/LP benchmark

This experiment uses the real BiGG `e_coli_core` model bundled with COBRApy 0.30.0, frozen at SBML SHA256 `13daac1b0ef19a12459371d4c11d16122ffaccf207070c08a6a66f8ba983b91f`. Organism: *Escherichia coli*, not human tissue or a tumor model.

## Research question

Does structure-aware SAT candidate exclusion and GPR-reaction signature memoization reduce total calls to a real GLPK metabolic LP oracle, while reproducing all minimal one-, two-, and three-gene biomass-disrupting knockout sets?

We use 32 gene candidates: the 18 one-to-one gene/reaction intervention genes from R2, plus 14 real genes involved in complex AND/OR rules from `GLCpts`, `ATPS4r`, `CYTBD`, `FBA` and `PDH`. Each rule comes from the published model, not an invented regulatory edge.

All 5,488 combinations of size 1-3 are exhaustively solved independently using native COBRApy gene knockout + GLPK biomass FBA. On every combination, we additionally remove the GPR-implied reaction set and require identical growth (absolute error <= 1e-7); this checks our Boolean interpretation against COBRApy's reference gene knockout operation.

**Endpoint:** biomass flux below 1% of wild-type in the fixed model environment. This is an in silico bacterial growth metric and **not** drug efficacy, tumor inhibition or clinical validation.

## Three paired SAT arms

The same CaDiCaL 1.9.5 wrapped by PySAT `python-sat==1.9.dev21` generates cardinality-constrained candidate gene knockout sets. Each setting is run 3 times, with rotated execution order, measuring complete wall time (including CNF, preprocessing and GLPK).

- `plain`: enumerate every possible candidate of size 1–3 using SAT, verifying its biomass with GLPK.
- `structural`: when a lethal subset S is found, add clause excluding all future supersets of S. This is safe because positive AND/OR GPR rules mean deleting more genes can never reactivate a reaction, and reaction removal cannot increase maximal biomass.
- `structural_memo`: same monotone SAT blocking plus cache of exact sets of reactions disabled by GPR. Two gene KOs disabling exactly the same reaction set represent the same GLPK feasible constraints and can reuse an already verified biomass value.

For all three arms, compare the **exact** minimal gene intervention sets with independently exhaustively tested results and abort if any mismatch. Metrics include candidate count, LP calls, memo hits, SAT calls, solver time, and paired wall time.

## Official gMISpy source check

A second job installs published `PlanesLab/cyclic-gMISpy` pinned to upstream commit `76ce96de9d4e18c8200876f5a73d3b2d60e4a012`; it calls the real `getGPRDict` and `boolTransformer` functions, extracting six complex gene-rule examples. A third job independently checks all corresponding truth-table valuations against the R3 parser and confirms the SBML source SHA matches.

**Critical limitation:** this does **not** run the entire cyclic gMISpy Gurobi/Bonesis intervention pipeline on identical tasks. Therefore no direct R3 speedup over gMISpy is claimed. The SAT core is CaDiCaL with an experimental DRNAS structural strategy, not native DRNAS. Furthermore, full optimization using human regulator interactions remains unimplemented.

## How to reproduce

```bash
python3 -m pip install cobra==0.30.0 python-sat==1.9.dev21
python3 research/drnas_medical/gmispy_r3.py benchmark --out medical-results/r3 --max-k 3 --repeats 3

python3 -m pip install 'git+https://github.com/PlanesLab/cyclic-gMISpy.git@76ce96de9d4e18c8200876f5a73d3b2d60e4a012'
python3 research/drnas_medical/gmispy_r3.py upstream-gpr --out medical-results/r3-upstream
```

GitHub workflow: `.github/workflows/drnas-medical-gmispy-r3.yml`.
