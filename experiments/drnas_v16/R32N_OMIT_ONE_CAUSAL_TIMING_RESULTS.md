# R32n — original-source-certified GF(2) one-unit omission timing

**Date:** 2026-11-03  
**Completed run, six SUCCESS jobs:** https://github.com/Frane12/AndroidGameTest/actions/runs/41653089760  
**All 2,100 trial rows and 65-source manifest:** https://github.com/Frane12/AndroidGameTest/actions/runs/41653089760/artifacts/13238572061  
**Branch:** `experiment/drnas-r32n-minimal-implication-20261103`.

## Scope, controls and caveats

We explicitly removed watchdogs, parallel solving, solvers communicating with
each other, process portfolios and search-policy edits. **Each measurement
runs exactly one pinned Kissat binary**. Six arms: clean Kissat, instrumented
native OFF, all certified original-CNF GF(2) root units, and full-minus-one
unit (`w4`, `w24`, `w48`). Full-minus-one is identical to full if the
named literal is not present in that source's certified root basis.
All interventions are performed *inside the pinned native solver parse
path*, and both native-off and all ablation modes have the **same** native
phase CPU timing / read-only R32l early-CDCL trace enabled.
Every inserted signed unit is independently re-derived from complete
parity-CNF plus original-source BCP, with exact literal sign checks.

65 SHA-distinct original CNFs = 5 previously seen R32e/R32l diagnostic
formulas (10 repeats each) + **60 entirely new synthetic generator
instances** (5 repeats each), total 2,100 trials on four CI shards.
The source solver `8af8e56f174b778aef3aa45af9f739b2a5f492c2`
is the same pinned upstream Kissat for both clean and modified binaries.
All attempted verdicts agreed, all SAT witnesses checked against their
original DIMACS; UNSAT labeled from generator reference, not LRAT.
No timeout. No official or external hard SAT benchmark is included.

**IMPORTANT**: the 60 new cases comprise 24 cases with **no** certified
root-unit intervention (control), 18 with **8** applicable root units,
and 18 with **12**. The `omit48` policy is *identical to full* on
all 8-unit sources because `w48` is not present. Do not interpret
those cases as evidence that `w48` is unnecessary.

## New 60 synthetics: complete paired wall benchmark

Five repeats per case, 300 attempts per mode, result in seconds.

| Single-solver mode | Summed wall (s) | Change vs native OFF |
|---|---:|---:|
| Clean original Kissat | 4.813045 | -0.45% |
| Native OFF / same trace instrument | **4.834718** | reference |
| **Full 8 or 12 certified units** | **4.596799** | **-4.9211%** |
| Full minus signed literal `4` | 4.788922 | -0.9472% |
| Full minus signed literal `24` | 4.794649 | -0.8288% |
| Full minus signed literal `48` | 4.708091 | -2.6191% |

Of 60 source medians, full was faster on only **17** and slower on **43**.
Bootstrap 95% case-resampled interval of the full-policy percentage
difference from native-OFF was **[-9.691%, -0.772%]**, conditional on
the particular synthetic source generator distribution and CI runner.
At millisecond latencies, the main gain is **concentrated on a handful
of solvable-by-lucky formulas**, not a uniform advantage. The 24
zero-applicability cases have 1.843245 s OFF versus 1.855474 s Full,
showing the overhead of a failed XOR attempt.

By applicable root units:
- **8-unit formulas (18)**: OFF 0.829717 s vs full 0.669959 s.
- **12-unit formulas (18)**: OFF 2.161756 s vs full 2.071366 s.
- **Zero applicable units (24)**: OFF 1.843245 s vs full 1.855474 s.

## Diagnostic source medians, milliseconds (five previously examined)

| Original SHA-frozen CNF | OFF | Full | Without w4 | Without w24 | Without w48 |
|---|---:|---:|---:|---:|---:|
| `r32l_stress_consistent_visible_331.cnf` | 23.226 | **3.567** | 23.918 | 24.151 | 23.975 |
| `r32l_stress_consistent_mixed_333.cnf` | 24.314 | **3.882** | 24.662 | 24.505 | 24.489 |
| `r32l_fresh_consistent_hidden_303.cnf` | 31.012 | **3.842** | 29.575 | 29.575 | **3.866** |
| `r32e_stress_consistent_mixed_53.cnf` | 33.001 | **21.894** | 33.208 | 22.970 | 33.431 |
| `r32e_stress_consistent_visible_51.cnf` | 32.715 | 33.229 | 33.169 | 33.081 | 33.557 |

These are *diagnostics, not unseen validation cases*. The first two
require each of the three probed units for the observed early-lucky
transition. Hidden303 tolerates omission of w48.

## New source: phase transition held on an entirely unseen 12-unit case

`r32n_base_consistent_visible_505.cnf` (12 certified unit literals):

| Root policy | Median wall ms | Phase solving returns in |
|---|---:|---|
| Native OFF | 17.500 | lucky late (after preprocessing) |
| Full 12 proven units | **3.152** | **lucky early** |
| Omit w4 (11 units) | 17.098 | lucky late |
| Omit w24 (11 units) | 17.509 | lucky late |
| Omit w48 (11 units) | 17.470 | lucky late |

The full policy is **~5.55x faster on this source** than native OFF.
This is a *fresh independent source* corroborating that multiple
separately entailed root literals can have a conjunctive effect on the
success of Kissat's early lucky probing route, avoiding preprocessing.

For the 60 new formulas, transition counts (unique sources):
- **Five** moved from `lucky_late` to `lucky_early` with full units.
- **One** moved from `cdcl` to `lucky_late`.
- Most remained in the same exit phase.
- `omit4` and `omit24` yielded **no new lucky-early transitions**
  compared with original OFF.
- `omit48` had **four** lucky-early transitions, all on 8-unit sources
  where w48 is not present, i.e. its omission is a no-op.

The new 60-source native preprocessing CPU cost dropped from
**3.425785s OFF** to **3.123742s full**, a 0.302043s saving,
while native CDCL CPU fell only from 0.350295s to 0.347481s.
This reinforces R32m's *preprocessing skipped or shortened* mechanism.

## Mechanistic conclusion

The special GF(2) consequence `w_i=1` is logically certified from
full local XOR3 blocks and root z-unit constraints; plain initial BCP
does not necessarily derive it. The earliest lucky forward/backward
probe heuristics can then succeed or fail based on **which set of
already-correct literals was fixed**. On a new 12-gadget source,
removing any one of three widely separated units destroys early lucky
success even though every remaining unit is mathematically sound.
Thus mathematical sufficiency (entailed units) and algorithmic
sufficiency (a particular lucky heuristic route) are distinct.

This test **does not prove global inclusion-minimality** of all twelve
units on the new case; we tested omissions w4,w24,w48 only.
The earlier all-12 leave-one-out checks in R32m's 2 known stress
diagnostics established deletion-minimality only for those particular
examples. These results do not establish broad official-SAT speedup,
world ranking, general NP complexity reduction, or P=NP.

## Next test: not a new process architecture

The next precise native-only instrumentation is in `lucky.c`:
record which one of forward_false/forward_true/backward_false/backward_true
succeeds, the first conflict-probe attempted literal, and the count of
probes before failure. Freeze a *new* external formula set with
original-CNF correctness/proof controls and realistic seconds-scale
solve times before trying an adaptive guard.
