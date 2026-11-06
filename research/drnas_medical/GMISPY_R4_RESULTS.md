# DRNAS Medical R4 — measured comparison versus Gurobi MIP (2026-11-06)

**Primary certified workflow:** https://github.com/Frane12/AndroidGameTest/actions/runs/42219637140

**Conclusion (scope-limited):** On the SAME published *E. coli* core metabolic model, the proposed SAT master with monotone structural cuts and GPR reaction-signature memoization was **3.22x faster in median whole-algorithm wall time** than a **custom Gurobi 12.0.3 MIP master with lazy constraint enumeration**. Both used the same GLPK metabolic flux oracle and both enumerated all 18 inclusion-minimal intervention sets. This is an algorithmic result on a real metabolic model; **not** a native DRNAS vs world-leading gMISpy speedup.

## Frozen test definition and independent audit

- Real COBRApy `textbook`/`BiGG e_coli_core` model, SHA256 `13daac1b0ef19a12459371d4c11d16122ffaccf207070c08a6a66f8ba983b91f`, same as R2/R3.
- 32 fixed genes, all 5,488 knockout combinations with 1, 2 or 3 genes, 95 reactions, 72 metabolites, 137 model genes in total.
- Wild-type biomass threshold: 1% relative to modeled wild-type; disruption is defined as maximum GLPK biomass below threshold, not a clinical target.
- 5,488 independent gene KOs versus GPR-derived reaction KOs verified via **10,976** GLPK FBA calls. Every gene KO growth output matched its separately evaluated reaction-equivalent KO.
- Same inclusion-minimal 18 gene-KO sets as frozen R3 baseline, independently verified by `gmispy_r4_verify.py`. GPR reaction-deactivation monotonicity checked for all in-scope assignments.
- Every solver arm uses the same monotone learned blocking cuts, identical deterministic signature memo key (disabled reactions from real complex AND/OR rules), identical GLPK function, and exact same candidate budget.
- SAT master: PySAT CaDiCaL 1.9.5, gene cardinality CNF, add-clause blocking; **not native DRNAS binary solver**.
- MIP master: Gurobi 12.0.3 single-thread, binary gene variables with cardinality constraint, one global enumeration per `k`, `MIPSOL` callback adding sound lazy cuts; **not optimized joint metabolic MILP**, and **not full gMISpy/BoNesis**.
- 3 paired runs with rotated method order on the same GitHub Actions runner. Each run completes enumerating all legal minimal results and uses the same exact independently checked objective definition. Candidate order may differ.

## Actual measured timings (seconds)

| Repeat | DRNAS-like SAT + LP | Gurobi lazy MIP + LP |
|---|---:|---:|
| 0 | 0.3286030 | 1.0832766 |
| 1 | 0.3247702 | 1.0586371 |
| 2 | 0.3324771 | 1.0492867 |
| **Median** | **0.3286030** | **1.0586371** |

`1.0586371 / 0.3286030 = 3.2216` aggregate median speed ratio in favor of SAT **for these two custom formulations only**.

Both methods: 2,730 enumerated candidate KO sets, 716 GLPK FBA calls, 2,014 cache hits, exactly 18 inclusion-minimal sets. The Gurobi callback was invoked with 2,736 MIPSOL candidate notifications due to extra revisitations; 2,730 unique candidates were evaluated. The SAT method made 2,733 solve calls including final UNSAT per knockout length.

Relative to the naive R3 SAT+LP algorithm that required 5,488 LP calls, BOTH optimized R4 algorithms needed only 716 LP calls (86.95% fewer); that reduction must **not** be credited solely to the SAT core, since both implemented the SAME biological GPR cache.

## Crucial scientific caveats

1. This is a frozen 32-gene subset in **bacterial metabolism**; it does not include tumor data, human regulatory networks, drug binding, or cell experiments.
2. Comparisons of sub-second algorithm times on three repetitions can be sensitive to runner noise and solver formulation choices.
3. The Gurobi MIP side is a reasonable strong external **binary optimizer** for a repeated no-good enumeration master, but not the best conceivable formulation of metabolic cut sets (e.g. specialized dualized MILP, column generation or complete upstream gMISpy). No claim of world-record or superiority over gMISpy is justified.
4. This tested **method architecture** rather than native DRNAS SAT source code.
5. The measurable advantage could disappear or invert on more difficult larger gene sets, different media, or alternative selection objectives.

## Independent CI proof

Verified `DRNAS_GMISPY_R4_CERTIFIED_CROSSCHECK: PASS` with 5,488 independent source-model KO queries and 18 frozen reference minimal intervention sets.
The GitHub run preserves full source SBML, exhaustive FBA comparisons, trial records and independent proof.

**Next defensible R5 direction:** compare with an externally optimized published MILP formulation for gene minimal cut sets, then scale to a well-specified human metabolic model. Focus on how often distinct gene-intervention choices collapse onto identical disabled-reaction signatures; compare cumulative FBA workload and proof completeness, not only elapsed time.
