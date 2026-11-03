# DRNAS R44 frozen early-checkpoint hint-dose selector — verified outcome

Date: 2026-11-03. GitHub Actions: https://github.com/Frane12/AndroidGameTest/actions/runs/41647287439

## Precommitted intervention

The experiment compares **one pinned CaDiCaL 3.0.1 native binary** with: frozen V9.1 quality gate, V9.1 quality-gated fixed 32-hint rescue, and R44 conservative 0/16/32-hint selection. A SHA-pinned original Kissat is the external comparator.

The R44 early-resume intervention requires the old V9.1 quality condition (learned >= 20; at least 6% LBD2; at least 32 propagations per conflict). For 32 hints, also require LBD2 fraction <= 12% and propagations/conflict <= 384. For 16 hints, require LBD2 fraction <= 20% and propagations/conflict <= 512. Otherwise abstain. Every selected dose is capped to the available candidates. The original V9.1 extended branch is unchanged. The rule was chosen with knowledge of R41-R43 results, **before** R44 formula selection and testing.

## Final locked test outcome

* 8 SHA-distinct **original SAT Competition 2026 formulas** (4 SAT/4 UNSAT); specifically excluded the preceding 38 frozen official originals, but not guaranteed unique against all earlier DRNAS work.
* 2 paired attempts per formula per mode; 64 native/Kissat trials; 15 s real-time timeout and PAR-2 = 30 s for timeout.
* Initial 256-conflict integer telemetry was identical in **16 of 16** comparable native pairs.
* **R44 adaptive: 0 of 16 early-resume activations, solved 0/16, mean PAR-2 30.000 s.**
* Fixed cap32: 2 of 16 early-resume activations, solved 0/16, mean PAR-2 30.000 s.
* Frozen V9.1: solved 0/16, mean PAR-2 30.000 s.
* Original Kissat: solved 2/16 (one UNSAT formula, two repetitions), mean PAR-2 26.6775 s; solved case ~3.42 s.
* The bootstrap statistic for R44-vs-V9.1 is degenerate [0,0], **not** evidence of true equivalence or non-inferiority: all 16 attempts in each mode timed out.

## Why R44 selected zero additional hints

This table is derived directly from the completed per-shard JSON diagnostics, not from hidden/guessed timings. Ratios describe the early checkpoint of repetition 0; the initial prefixes were identical across native modes, and both repetitions produced the same dose decision.

| Original ID prefix | Official label | Extended after first checkpoint? | Original V9.1 quality signal | LBD2 share | Propagations/conflict | R44 new early dose | Fixed cap32 new early dose |
|---|---|---|---|---:|---:|---:|---:|
| 1236c140 | SAT | Yes | No | 0.41% | 24.43 | 0 | 0 |
| 805a742e | UNSAT | Yes | No | 0.00% | 38.11 | 0 | 0 |
| ae48df65 | UNSAT | No | No | 2.77% | 222.45 | 0 | 0 |
| 4ae685a1 | SAT | Yes | Yes | 7.57% | 99.77 | 0 | 0 |
| 1397d1d4 | UNSAT | No | No | 0.00% | 72.60 | 0 | 0 |
| 7fa502df | SAT | No | Yes | 37.71% | 2033.33 | 0 | 32 |
| b023ea0e | UNSAT | Yes | Yes | 23.39% | 89.63 | 0 | 0 |
| ab17eed9 | SAT | Yes | No | 0.00% | 22.06 | 0 | 0 |

The cases 4ae685a1 and b023ea0e follow the **old V9.1 extended route** and are not opportunities for the *new* early-resume intervention. The only case satisfying the old positive quality test on early-resume, 7fa502df, had exceptionally high LBD2 share and propagation intensity. The frozen R44 risk filter abstained, whereas fixed cap32 applied 32 hints. Both timed out; this is not a demonstrated improvement.

## Research interpretation

R44 validates implementation and pre-intervention parity, and it confirms a conservative *abstention*. It **does not validate predictive utility, speedup, or a universal law** because the active policy made no new intervention on the eight tested formulas and none of the native modes finished within the cap.

The official source/runtime/size filtering is non-representative. The source code and thresholds should remain unchanged for this experiment; a *separately named* prospective design must choose solver-tractable, diverse instances and a sufficiently informative horizon to evaluate actual impacts. No numerical world-record or parity claim can be inferred from this result.
