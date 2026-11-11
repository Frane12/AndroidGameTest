# DRNAS ATLAS39 CUM1 — Final independent audit findings

2026-11-11. All six benchmark shards completed successfully in the immutable
[260-trial GitHub Actions run](https://github.com/Frane12/AndroidGameTest/actions/runs/43033156777).
The first audit job of that run failed because `actions/checkout` was placed
*after* `actions/download-artifact`, deleting untracked audit files.
A separate [successful audit-only recovery](https://github.com/Frane12/AndroidGameTest/actions/runs/43033807202)
read the unchanged six benchmark artifacts and verified the matched SHA,
260 trial completeness and original SAT witness flags. The original workflow
is **not** an entirely green run; do not imply it is.

## Experiment and mechanistic checks

- Native DRNAS C7 with fixed 75%-of-baseline deletion quota.
- A39_SHADOW records valid learned reason reads encountered by conflict
  minimization; it does not modify deletion ordering.
- A39_PROTECT discounts the baseline candidate score by 500 if a clause
  has at least two learned-reason reads in a 4,500-conflict window.
- All original learned-reason locking, glue/low-LBD and short clause
  protections are unchanged. Metadata migrates with clause CID compaction.
- Only the new modes pay the telemetry cost. Memory peak for utility metadata
  <= 230,560 bytes (reported on these inputs; not a universal bound).
- 26 original SHA × 2 seeds × 5 arms = **260 actual trials**; original SAT
  witness verification; single logical CPU per process.
- Original regression 10 SHA, original extension 6 SHA, new additional
  hard indices 12/13 from 5 SATLIB families (10 SHA). The last cohort is
  prospective relative to ATLAS37 but **not globally blind**.
- All UNSAT returned by plain CDCL/Kissat remains unverified by an
  independently checked LRAT certificate. Reported PAR2 and strict
  SAT-witness-only verified PAR2 are not interchangeable.

### Verified cohort totals

| Cohort | Solver | Verified SAT | Unverified UNSAT | Solved reported | Reported PAR2 s | Verified PAR2 s | E2E sum s |
|---|---|---:|---:|---:|---:|---:|---:|
| Regression (20/arm) | Kissat | 12 | 8 | 20 | 13.244805 | 160.407385 | 13.244805 |
| Regression | C7 | 12 | 6 | 18 | 71.597694 | 173.687554 | 51.613628 |
| Regression | A36_75 | 11 | 6 | 17 | 88.630834 | 189.720602 | 58.657347 |
| Regression | A39_SHADOW | 11 | 5 | 16 | 98.802628 | 189.751620 | 58.838181 |
| Regression | A39_PROTECT | **12** | 6 | **18** | **71.261152** | **173.555705** | **51.277653** |
| Extension (12/arm) | Kissat | 8 | 4 | 12 | 8.560914 | 96.970094 | 8.560914 |
| Extension | C7 | 6 | 2 | 8 | 122.995942 | 164.342917 | 75.031523 |
| Extension | A36_75 | 8 | 2 | 10 | **65.008367** | **106.073542** | 41.026461 |
| Extension | A39_SHADOW | 8 | 2 | 10 | 65.211750 | 106.235169 | 41.230357 |
| Extension | A39_PROTECT | 8 | 2 | 10 | **81.022066** | **122.268663** | 57.039216 |
| Hard (20/arm) | Kissat | 12 | 8 | 20 | 20.458015 | 192.842793 | 20.458015 |
| Hard | C7 | 12 | 4 | 16 | **107.003153** | **202.958891** | 59.045492 |
| Hard | A36_75 | 12 | 4 | 16 | 109.265841 | 205.223007 | 61.310528 |
| Hard | A39_SHADOW | 12 | 4 | 16 | 109.452765 | 205.409887 | 61.497096 |
| Hard | A39_PROTECT | 12 | 4 | 16 | 110.634847 | 206.592120 | 62.681574 |

### Overall per-arm totals across 52 attempts

| Arm | SAT verified | UNSAT unverified | Reported solved | Reported PAR2 s | Verified PAR2 s |
|---|---:|---:|---:|---:|---:|
| Kissat | 32 | 20 | 52 | 42.263734 | 450.220272 |
| C7 | 30 | 12 | 42 | 301.596789 | 540.989362 |
| A36_75 | 31 | 12 | 43 | 262.905042 | 501.017151 |
| A39_SHADOW | 31 | 11 | 42 | 273.467143 | 501.396676 |
| A39_PROTECT | **32** | 12 | **44** | 262.918065 | 502.416488 |

**Interpretation:** despite one more original SAT witness, the aggregate
reported PAR2 for PROTECT is essentially identical to A36_75 (+0.013 s),
and strict SAT-witness-only verified PAR2 is **1.399 s worse**.
Kissat remains much faster in E2E/reported PAR2 and solves all 52 reported
attempts, but those include 20 independently *unverified* UNSAT results.

### Specific changes from the actual original SHA logs

- `uf250-1065` index **0**, SHA `be9bb6443c9c...`, two reps:
  A36_75 timeout 10 s / SAT 5.011 s,
  A39_PROTECT SAT **0.596 s / 0.743 s**. The verified PAR2 improvement
  is **23.671 s**, a very promising local win.
- `uf250-1065` index **10**, SHA `86fcdd447ce725...`:
  A36_75 SAT **2.246 / 0.355 s**,
  A39_PROTECT SAT **7.460 / 10.249 s**; **15.109 s worse** combined,
  and 170,373 more measured conflicts.
- `uf250-1065` index **1**, SHA `1e3bf30ef02a...`:
  one seed regresses from SAT 0.217 to 9.500 s,
  the other improves from SAT 4.349 to 2.572 s.
- `uf250-1065` index **11**, SHA `aa0c7b9083f68d...`:
  4.624 -> 6.140 s on seed 1, 2.787 -> 2.357 on seed 2.
- `uuf250-1065` index **1** has a combined ~1.205 s reported
  improvement, but neither UNSAT result has independent LRAT.
- `uf250-1065` indices **12/13** are new hard controls; neither
  achieves a consistent improvement across both seeds.
- The all-cohort sum of **253,677 rank reassignments** counts deletion
  selection changes *across reduction events*, not distinct CIDs.

### Mechanism and next algorithmic question

- Reason-use history is a real, active signal: PROTECT changed the
  deletion set, not merely CPU timing. SHADOW reproduces the same
  conflict counts as A36_75 on the completed paired cases, which
  helps isolate monitoring overhead.
- But a high rate of recent minimization-reason reads is not reliably
  predictive of future benefit from protecting a clause. The same
  fixed threshold produces spectacular wins and large losses.
- The feature is also incomplete: it samples reasons used by the
  minimizer, not *all* BCP reasons or identical-clause relearning.
- Memory is modest, but added C++ instrumentation and sorting cost
  must always be included in E2E. Timeout telemetry may be missing,
  so aggregate conflict counters are not fully comparable across
  different timeout counts.

**Decision:** Do **not** promote C39_PROTECT into the stable standalone
solver. Retain the A36_75 control. Study clause reason-use *relative to
LBD and age* and measure utility under repeated independent hard SHA,
preferably with a freeze-threshold ablation and explicit original-CNF
proofs. Avoid training the next heuristic on these already inspected
source SHA and then calling that validation blind.
