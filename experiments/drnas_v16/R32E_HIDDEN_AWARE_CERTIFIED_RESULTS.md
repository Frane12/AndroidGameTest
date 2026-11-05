# DRNAS SAT R32e: independently certified hidden-aware GF(2) root interventions

**Audit run (PASS):** https://github.com/Frane12/AndroidGameTest/actions/runs/41638482746  
**Final SHA-pinned artifact (3024 paired attempts):** https://github.com/Frane12/AndroidGameTest/actions/runs/41638482746/artifacts/13231836689  
**Experimental branch:** experiment/drnas-r32e-hidden-aware-20261103  
**Date:** 2026-11-03.

## Protocol and limits

R32e builds pinned upstream Kissat at `8af8e56f174b778aef3aa45af9f739b2a5f492c2`
and pairs **six modes**: clean original Kissat, native OFF, R32b passive,
R32c all-safe-root-active, R32d direct-only gate, and R32e hidden-resolvent-aware gate.

- **70 SHA-distinct new original synthetic CNFs**: 42 baseline held-out generator seeds
  (10 repeats each) plus 28 source-coupled synthetic stress instances (3 repeats each).
- 504 paired trials per mode, **3,024 completed attempts**, four shards, one frozen manifest,
  matching binary SHA fingerprints, process-affinity pinned, randomized mode order.
- Limit 8 seconds per attempt; 16-second PAR-2 penalty; **no timeouts**.
- R32e root units are permitted only for a consistent, independently verifiable GF(2)
  system with 8–12 additional units, 16–96 source equations and either no
  hidden resolvents or at least two resolutions per extra unit.
  All injected signed literals were checked against a separate original-CNF proof.
  Contradiction and incomplete-XOR signals abstain.
- SAT outputs were checked by an independent witness against the original DIMACS.
  UNSAT was checked against the generator's original label; **no LRAT UNSAT proof**.
- This is a **synthetic blind-seed evaluation**, not an independent industrial or
  SAT Competition 2026 result. It does not prove a universal speedup or P=NP.

## Aggregated wall time (seconds; smaller is better)

| Cohort | Clean Kissat | Native OFF | R32b passive | R32c active | R32d gate | R32e gate | R32e vs OFF |
|---|---:|---:|---:|---:|---:|---:|---:|
| All 70 | 12.506899 | 12.532960 | 12.606330 | 12.494996 | 12.504819 | **12.466949** | **-0.5267%** |
| 42 new baseline | 8.689899 | 8.711500 | 8.753972 | 8.669429 | 8.685170 | **8.662778** | **-0.5593%** |
| 28 new coupled stress | 3.817000 | 3.821460 | 3.852358 | 3.825567 | 3.819649 | **3.804171** | **-0.4524%** |
| Consistent visible XOR | 1.219153 | 1.218154 | 1.222021 | 1.221253 | 1.222357 | 1.224988 | +0.5610% |
| Consistent hidden XOR | 1.013389 | 1.015244 | 1.027640 | 0.988070 | 1.036022 | **0.993971** | **-2.0954%** |
| Consistent mixed XOR | 0.986437 | 0.986785 | 1.009191 | 0.905601 | 0.908335 | **0.905426** | **-8.2449%** |

The complete artifact also includes conditional XOR, contradictory-root XOR,
incomplete XOR decoys, and non-XOR planted-random3 controls. R32e worsened
the contradictory root category by **+6.491%** (no units were injected),
which shows the importance of probe overhead/abstention costs.

## Mechanism-sensitive case: genuine changes in CDCL search

`r32e_stress_consistent_mixed_53.cnf` (new synthetic SHA identity):

| Mode | Median total wall time (s) | Final CDCL conflicts |
|---|---:|---:|
| Native OFF | 0.027705 | 27 |
| R32c active | 0.018551 | 0 |
| R32d selective | 0.018430 | 0 |
| **R32e selective** | **0.018409** | **0** |

All three independently started R32e trials on the same source had zero
conflicts and times 0.018409, 0.018367, 0.018422 seconds.
Median change is **-33.55%** versus Native OFF. The original CNF model check
passed. The source's root derivation carries 12 certified unit literals.
This is a real controlled solver-work reduction on **one synthetic case**,
not evidence of general performance on hard industrial SAT instances.

**Counterexample:** `r32e_stress_consistent_visible_51.cnf` saw final
conflicts increase **21 → 56**, while median time rose from 0.033257 s
to 0.033534 s (**+0.83%**). Correct units can harm a CDCL trajectory.

## Statistical interpretation

- Overall R32e wall-time PAR-2 sum: **0.5267% lower** than Native OFF.
- **14/70** individual source median times improved.
- Bootstrap across source medians: **95% interval [-1.755%, +0.632%]**.
  The interval crosses zero, so there is **no confirmed aggregate general
  speed advantage** at this study size even though some individual effects
  are strong.
- Baseline-cohort interval **[-2.563%, +0.886%]**; coupled-stress-cohort
  interval **[-2.435%, +0.956%]**.
- 70/70 solved in all modes, no timeouts. All 6 workflow jobs succeeded.

## Next falsifiable milestone

Do not optimize the selector based on its 70 holdout labels.
Instrument the *preprocessing state* and the *early implication/learned-clause
graph* to distinguish genuine causal gain from time noise and incidental
lucky preprocessing. Freeze a new rule from a separate development suite,
then verify on external medium-difficulty official SAT/Crypto instances at
30–120s caps. Demand independently checked UNSAT certificates or refrain
from interpreting unverified UNSAT speed differences.
