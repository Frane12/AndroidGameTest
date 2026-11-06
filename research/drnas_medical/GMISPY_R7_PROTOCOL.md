# DRNAS Medical R7 — original gMCSpy vs GPR-exact flux-witness SAT

Status: **new hypothesis**, not a claimed speedup. No medical efficacy claim.

## Frozen biological benchmark

BiGG E. coli core (COBRApy textbook), 95 reactions, 72 metabolites, 137 genes. Source SBML SHA256: 13daac1b0ef19a12459371d4c11d16122ffaccf207070c08a6a66f8ba983b91f. Same 48 and 64 authentic locus-gene cohorts from certified R6, excluding non-intervenable pseudo-gene s0001. Gene KO sizes 1–3, biomass suppressed below 1% of wild-type, original fixed medium. An independent full gene-level and GPR-implied reaction-level GLPK oracle checks 18,472 and 43,744 candidate sets, yielding exactly 25 and 70 minimal solutions.

These cohorts overlap and are from a bacterial model. No human tumor model, no clinical data.

## Motivation

R6 original published specialist gMCSpy prevailed 12.68× (48) and 26.01× (64) over R6 SAT + candidate FBA. Its dual formulation is specialized and avoids repeatedly optimizing each KO. We want to test whether learning **sound biological information** in SAT can close that gap.

## Algorithm: primal flux witness, not a dual MILP

Reify GPR AND/OR reaction activity exactly with Boolean Tseitin SAT constraints, keeping all nontargeted genes active. When a tested KO is viable, ask GLPK for its *full flux vector* supporting biomass. To invalidate this feasible flux, at least one reaction with nonzero flux that can be disabled by the selected gene cohort must be knocked out. Add a global SAT disjunction of reaction-disabled literals for every such reaction. Learn the wild-type flux first; reuse all witness cuts at KO cardinalities 1, 2 and 3. Each genuinely lethal KO yields a superset-blocking clause. Conclusive SAT UNSAT ensures no further KO set of size at most three, provided each flux witness remains valid for unchanged knockout-medium semantics.

The resulting algorithm is CEGAR on primal metabolic witnesses. **It is not yet** a SAT transcription of the original gMCSpy G/F dual-MILP. It is not native DRNAS SAT (engine: PySAT CaDiCaL) or full cyclic regulatory gMISpy (which also includes gene knock-ins).

## Fair test

Three interleaved repetitions each, same runner and source genes:
1. R7 flux-witness PySAT/GLPK.
2. R6 original SAT per-candidate GLPK with structural memo.
3. Published original PlanesLab/gMCSpy at upstream commit 4567a6d14bd2e5517e7a86b17aebefb0f285544c, calculateGeneMCS, staged-lazy mode, Gurobi 12.0.3, single thread.

Full solver wall times (including R7 GPR-to-CNF preprocessing and published gMCSpy G/F preprocessing), all LP calls, learned flux clauses, exact returned sets and provenance retained. Independent CI job verifies exact reference, original specialist completion, repeats and medians. No competitive speed claim without all checks passing. If the method fails, the failed result is valuable evidence for implementing true certified dual SAT and testing distinct held-out metabolic networks.

Future cancer research requires independently curated human GEM/DepMap evidence and biological validation; none is present in this R7 bacterial benchmark.

Scientific reference: https://doi.org/10.1093/bioinformatics/btae318
Original software: https://github.com/PlanesLab/gMCSpy
Methodology review: https://pmc.ncbi.nlm.nih.gov/articles/PMC12014531/
