# DRNAS SAT R27/R27b/R27c — verified XOR ↔ AND polynomial structure

Date: 2026-11-03. Experimental branch: `experiment/drnas-r27-xor-residual-links-20261103`.

## Question

Why does the R26 exact-GF(2) fastpath work on clean XOR formulas but not on authentic polynomial multiplication SAT CNFs? Is there a precise, useful link between parity constraints and the remainder?

## Proven from original source CNFs

Sources: the same 10 original, SHA-256-locked Global Benchmark Database polynomial multiplication CNFs used in R26. No solution labels, filenames, results or timings were used to classify structures. The existing 53-formula frozen manifest and original SAT/R26 timing artifacts were reused without changing measured inputs.

1. R27 extracted **complete forbidden-polarity patterns** constituting certified XOR equations. On each original polynomial formula, about 40–49% of original clauses belong to those complete XOR patterns. Pure XOR controls have 100% exact-XOR coverage and no XOR/residual interface.
2. R27b established for **all ten** polynomial sources that every output/interface variable occurs in **exactly four** residual clauses, each crossing residual clause contains exactly one XOR variable, and across each formula the crossing residuals comprise exactly **3N binary** clauses and **N quaternary** clauses for **N interface variables**.
3. R27c grouped the four original residual clauses around each interface output variable and independently replayed the full **16-state truth table**. All **109,319 interface groups** across the ten authentic CNFs proved EXACT three-input AND gates, with input literals possibly negated. There were **zero** unclassified groups, **zero** OR gates and no non-crossing residual clauses in these cases.
4. Together, the CNF describes a network of XOR equations connected to nonlinear three-input AND outputs. The equation `g = l1 AND l2 AND l3` translates in GF(2) to `g = product_i(l_i)`, with negative literals represented as `1 XOR variable`. Substituting gate outputs into XOR equations yields nonlinear degree-at-most-three algebraic constraints, not pure linear equations solvable by Gaussian elimination alone.

### Exact four-clause gate identity

For arbitrary signed input literals `l1, l2, l3`, the CNF

```
(-g OR l1)
(-g OR l2)
(-g OR l3)
( g OR -l1 OR -l2 OR -l3)
```

is logically equivalent to `g = l1 AND l2 AND l3`. The R27c script tests all 16 assignments of the output and three distinct input variables for each recognized gate.

## High-contrast original formula: mp1-Nb6T28.cnf.xz (SAT)

- 10,296 complete XOR blocks, comprising 48.148% of clauses
- 11,088 *verified* three-input AND gate outputs acting as XOR/residual interface variables
- 33,264 residual binary clauses plus 11,088 residual quaternary clauses
- 9,504 XOR equations reference one AND output, and 792 reference two AND outputs
- Old matched 10-second-cap R26 run: CaDiCaL 3.0.1 0.249419 and 0.245057 seconds, median 0.247238 s; Kissat 4.0.4 timed out twice (PAR2 20 seconds), and R26 also timed out.
- Neighboring mp1-Nb6T27 and mp1-Nb6T29 have closely similar gate/XOR counts but CaDiCaL timed out twice on each. This **does not establish** why the runtime varies; static degree/size features alone cannot explain the contrast.

| CNF | XOR blocks | Proven AND gates | CaDiCaL PAR2, 10 s cap | Kissat PAR2 |
|---|---:|---:|---:|---:|
| mp1-Nb6T27 | 9,900 | 10,692 | 20.000 s | 20.000 s |
| mp1-Nb6T28 | 10,296 | 11,088 | 0.247 s | 20.000 s |
| mp1-Nb6T29 | 10,692 | 11,484 | 20.000 s | 20.000 s |

## Reproducible actions & raw evidence

- R27 exact GF(2)/residual interface mapping: `https://github.com/Frane12/AndroidGameTest/actions/runs/41612160837`
- Recovered 17-source paired structural/timing report: `https://github.com/Frane12/AndroidGameTest/actions/runs/41612453350/artifacts/13219039452`
- R27b original ten-formula degree-motif report: `https://github.com/Frane12/AndroidGameTest/actions/runs/41612791947/artifacts/13220440037`
- R27c complete 109,319 AND-gate truth table audit: `https://github.com/Frane12/AndroidGameTest/actions/runs/41613176959/artifacts/13220310973`

Scripts: `r27_xor_residual_links.py`, `r27_links_report.py`, `r27_bridge_motifs.py`, `r27_gate_circuits.py`.

## Next experiment (not yet implemented as a solving speedup)

R28 proposal: instrument the exact **AND → XOR interface** during *early CDCL propagation* (e.g. first 256/512/1024 conflicts), measuring which gate assignments and parity consequences actually propagate, stalls, conflicts and branch decisions. In same-hardware matched A/B runs compare original CaDiCaL/Kissat and conservatively enabled gate/XOR propagation with safe fallback on fresh SHA-disjoint authentic polynomial CNFs. Predeclare the intervention and measurement sets before evaluating improvements. Use SAT model verification / independent UNSAT validation. No world-record or general NP acceleration is established by the structural audit alone.
