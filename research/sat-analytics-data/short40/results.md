# DRNAS SAT V15.3.1 — 40 external short SATLIB problems
Frozen before measuring; public external SATLIB benchmark, **not official competition**.
Source mitchellh/go-sat @ fc0e735aff48989326f256121b5ed6fc585858c3
40 distinct source-file hashes, four categories × 10; 2 solvers × 3 repetitions; 8 s cap.
Each paired solver comparison is made within one GitHub runner per family.
SAT checked against original clauses; DRNAS native UNSAT checked where proof emitted.
Kissat UNSAT and DRNAS Kissat-fallback UNSAT labels do **not** constitute independently verified UNSAT proofs.
Not known globally unseen across historical experiments; 13–20 previously used in the V15.3.1 baseline were excluded.
Input validation exclusion: dubois100.cnf has 598 clauses against claimed 800; replaced with dubois21.cnf before new timing.

| Family | Solver | Correct attempts | Timeouts | PAR-2 total (s) | Median wall (s) |
|---|---|---:|---:|---:|---:|
| uniform_sat | kissat | 30/30 | 0 | 0.044692 | 0.001418 |
| uniform_sat | v1531 | 30/30 | 0 | 0.072196 | 0.002335 |
| graph_coloring | kissat | 30/30 | 0 | 0.363998 | 0.011216 |
| graph_coloring | v1531 | 30/30 | 0 | 0.444913 | 0.013974 |
| uniform_unsat | kissat | 30/30 | 0 | 0.089252 | 0.002938 |
| uniform_unsat | v1531 | 30/30 | 0 | 0.121561 | 0.004038 |
| dubois_unsat | kissat | 30/30 | 0 | 0.062964 | 0.002115 |
| dubois_unsat | v1531 | 30/30 | 0 | 0.049645 | 0.001659 |

## Paired category speedup (Kissat PAR-2 / V15.3.1 PAR-2)
- uniform_sat: 0.6190x
- graph_coloring: 0.8181x
- uniform_unsat: 0.7342x
- dubois_unsat: 1.2683x
