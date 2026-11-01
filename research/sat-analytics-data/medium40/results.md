# DRNAS SAT V15.3.1 — external calibrated medium40
Four SATLIB public source families, 10 each, 3 repeats × 2 solvers = 240 measurements.
Original archive SHA1 pinned; solver baseline unchanged; matched comparisons per same runner.
Cases were chosen by **original Kissat-only pilot time**, not V15.3.1.
Window 0.1–5.0 s is a target, not a guaranteed achieved property. Out-of-window fallbacks shown.
Calibrated selection is NOT a strictly blind holdout or official SAT Competition result.
SAT witnesses validated; native DRNAS UNSAT proof checked where available. No independent
UNSAT proof validation for original Kissat or Kissat fallback in this experiment.

| Family | In target /10 | Solver | Correct /30 | Timeouts | PAR-2 (s) | Median (s) |
|---|---:|---|---:|---:|---:|---:|
| uf200-860 | 10/10 | kissat | 30/30 | 0 | 8.018382 | 0.253924 |
| uf200-860 | 10/10 | v1531 | 30/30 | 0 | 8.088441 | 0.256456 |
| uf250-1065 | 10/10 | kissat | 30/30 | 0 | 26.882897 | 0.896071 |
| uf250-1065 | 10/10 | v1531 | 30/30 | 0 | 26.939963 | 0.899363 |
| uuf200-860 | 10/10 | kissat | 30/30 | 0 | 11.903602 | 0.392391 |
| uuf200-860 | 10/10 | v1531 | 30/30 | 0 | 11.931424 | 0.377892 |
| uuf250-1065 | 10/10 | kissat | 30/30 | 0 | 76.303112 | 2.416893 |
| uuf250-1065 | 10/10 | v1531 | 30/30 | 0 | 76.359318 | 2.418401 |

## Paired PAR-2 speedup (Kissat/V15.3.1; >1 means DRNAS faster)
- uf200-860: 0.9913x
- uf250-1065: 0.9979x
- uuf200-860: 0.9977x
- uuf250-1065: 0.9993x
