# DRNAS SAT v9.5 — critical 96-conflict checkpoint vs dual-state falsification
2026-10-31
Completed **matched control** GitHub run: https://github.com/Frane12/AndroidGameTest/actions/runs/41236927249
Initial paid dual benchmark: https://github.com/Frane12/AndroidGameTest/actions/runs/41236194691

## Benchmark protocol
Twelve authentic SAT Competition 2026 CNFs previously used in v9.4, 6 verified SAT + 6 verified UNSAT, 4 modes × 2 repetitions = 96 runs. 15s wall clock budget, each timeout counted as 30s PAR2. Same pinned instrumented CaDiCaL 3.0.1 and frozen v7.6 controls. Four GH Ubuntu shards with one CPU affinity. Formulas verified by original SHA256.

## Final results (96 matched executions)
| Mode | Solved/24 | Mean PAR2 s | Sum of 12 formula mean PAR2 s |
|---|---:|---:|---:|
| v95_single_plain_checkpoint | **16/24** | **12.52492** | **150.29908** |
| v95_dual_probe | 14/24 | 14.55006 | 174.60075 |
| orig_v76_plain (frozen) | 12/24 | 16.93993 | 203.27920 |
| ca_plain | 12/24 | 17.33002 | 207.96029 |

Single 96-conflict plain checkpoint has ~27.73% lower mean PAR2 than unmodified plain CaDiCaL on this previously-viewed, size-filtered set and solves 4 additional attempts (two more distinct CNFs at 2/2 each). It also has ~13.92% lower mean PAR2 and 2 more solved attempts than dual 96+96. These numbers are descriptive; no statistical generality claim.

## Mechanistic attribution
- All completed dual attempts with reporting selected **plain** (14 completed/24); 10 timeout attempts do not expose a gate decision and CANNOT be assumed to have selected plain or sparse.
- 9ef9243f... SAT: CaDiCaL and original V7.6 plain both PAR2=30s/timeout; single-96 finishes 1.761s, dual 1.814s.
- 2b35377a... SAT: both baselines PAR2=30s/timeout; single-96 5.608s and dual 5.647s.
- 5de866bc... SAT: CaDiCaL 0.865s, original V7.6 0.705s, single-96 0.114s, dual 0.122s.
- 12cd0c31... UNSAT: CaDiCaL 8.415s, V7.6 plain 6.486s, single-96 7.069s, dual did NOT finish within 15s. The dual's chosen mode on this timeout is UNKNOWN.
- One 96-conflict checkpoint with continuation of the SAME CaDiCaL solver state reproduces the major wins without the extra Sparse probe. The evidence therefore supports the importance of checkpoint/resume behavior, NOT reliable automatic choice of hints.
- Both plain-only checkpoint and dual approaches may change the search trajectory due to CaDiCaL's internal limit / restart / resumption logic; these results do not show that LBD-based selection predicts general solver performance.

## Scientific limitations
The cohort already appeared in v9.4. The same CNF input can produce larger or smaller wall times across runner shards, and there are only two repeats. Original verified SAT/UNSAT labels and solver answers agree; no independent LRAT/DRAT UNSAT proofs collected. This is not an official SAT Competition submission, not a world record, not a broad claim of outperforming CaDiCaL.

## Recommended next prespecified experiment
Precommit a budgeted family of single-solver checkpoint options 64, 96, 128, 256 conflicts and an uninterrupted CaDiCaL control, then test on a NEW disjoint official 2026 benchmark cohort (not the prior 30); sample both SAT and UNSAT from multiple source families, explicit timeout penalties, and measure memory and CPU overhead. Do not select the best budget based on these already-viewed 12 CNFs and pretend the resulting optimization is blind.
