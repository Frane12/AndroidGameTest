# DRNAS SAT R32h–R32j: certified cooperative portfolios, watchdog and measurement audit

**Date:** 2026-11-03  
**R32h run:** https://github.com/Frane12/AndroidGameTest/actions/runs/41643426261  
**R32i run:** https://github.com/Frane12/AndroidGameTest/actions/runs/41644178338  
**R32j corrected run:** https://github.com/Frane12/AndroidGameTest/actions/runs/41644573660  
**R32j artifact (all 882 rows):** https://github.com/Frane12/AndroidGameTest/actions/runs/41644573660/artifacts/13234142437

## What changed

R32g cooperative relay **killed the existing native OFF solver**, then restarted it with
independently certified original-CNF XOR root units, thereby losing all existing CDCL state.

- **R32h**: never interrupt the two original solvers for an XOR message. When both
  are still working and the signed root literals are independently certified, an
  optional *third* helper on an isolated core can solve original CNF + entailed units.
  It preserves both original search histories. This is **not** in-process learned-
  clause exchange.
- **R32i**: start original OFF at t=0, delay the R32e certified XOR producer by
  12ms, kill only *the unneeded producer* after its own source signal says no GF2
  intervention is selected; preserve native OFF always. Permit a third helper
  only if both original workers are still active at 100ms.
- **R32j**: fix an important time-measurement confound. Prior solo trials used
  `Popen.wait(timeout=CAP)`, which polls with an adaptive sleep backoff;
  concurrent trials used a frequent `Popen.poll()` loop. This spuriously
  inflated the single solver latency and made R32i look faster.
  R32j applies the **same 500-microsecond monotonic polling loop** to every
  mode, with a new, SHA-frozen synthetic holdout.

## R32h audit (42 new synthetic sources × 3 repeats × 6 modes = 756 attempts)

All shard jobs and audit PASS. Native OFF total 5.074491s; non-destructive
third-worker total 5.181069s (**+2.1003%**); destructive R32g-style relay
5.371569s (**+5.8543%**); independent race 5.167012s (**+1.8233%**).

There were 66 actual third-worker launches in 126 non-destructive portfolio
trials; the third worker won only **1**. Overall helper CPU consumption
was **+212.4506%** relative to solo OFF. This was a useful architectural
safety result but not a practical optimization.

**CAUTION**: R32h was measured before the solo wait/poll audit below, so
do not interpret the R32h relative percentages as reliable speed ratios.

## R32i methodological warning

The first R32i implementation appeared to improve wall time **-16.065%**
relative to the solo native OFF mode on 42 fresh synthetics and 882 trials.
But its solo and concurrent arms used different waiting/polling code paths.
Since the solo Python `wait(timeout)` may report process exit later than the
frequent parallel `poll()`, this result **is not accepted as a solver speedup**.
The timing-protocol fix was committed BEFORE generating R32j's new holdout.

## R32j corrected matched-protocol benchmark

- **42 new SHA-unique synthetic sources**, 3 repeats, 7 solver modes = **882 attempts**.
- Identical 500µs monotonic polling in all arms; 8-second time cap, PAR2=16 seconds.
- 0 timeouts; all 6 GitHub jobs and all original-CNF source checks passed.
- Solver SHAs pinned to R32e pair; native OFF and R32e model outputs checked on
  original DIMACS when SAT; UNSAT uses original generator expected label.
- All root unit messages checked for exact signed literal soundness before
  possible relay.
- Every total includes process launch and polling, and child CPU time is counted.

| Policy | Total summed wall / PAR2 (s) | Change vs native OFF | Child CPU (s) | CPU change vs OFF |
|---|---:|---:|---:|---:|
| Clean Kissat | 3.170032 | -0.363% | 3.000257 | -0.245% |
| Native OFF Kissat | **3.181595** | baseline | **3.007630** | baseline |
| R32e solo active | 3.222433 | +1.283% | 3.054825 | +1.569% |
| Independent two-worker race | 4.095473 | +28.7239% | 7.604475 | +152.8394% |
| Destructive R32g-style relay | 4.320576 | +35.7991% | 7.909878 | +162.9937% |
| Non-destructive R32h-style third helper | 4.118936 | +29.4614% | 9.144536 | +204.0446% |
| **R32j deferred XOR watchdog** | **3.658625** | **+14.9934%** | **5.430605** | **+80.5609%** |

The frozen R32j watchdog policy delays the native GF2 producer until 12ms
into an unsolved original run and refrains from spawning a third helper until
both original tasks remain unsolved past 100ms. In 126 watchdog attempts,
**85 producers were launched**, 12 were cancelled after a useless-XOR gate,
and **no third helpers** started. OFF won 125/126 watchdog attempts; the
R32e producer won 1/126. This benchmark therefore validates the watchdog
abstention and scheduling mechanics, but not a useful later-stage helper
clause exchange on difficult formulas.

Descriptive bootstrap by source median (42 independently seeded synthetic
sources): **95% interval for R32j vs solo OFF +12.158% to +18.266%**.
Only 7/42 source medians were faster with watchdog.

## Research conclusion

A sound XOR lemma can shorten **individual CDCL trajectories**, as witnessed
by R32e's 27-to-0 conflict case, but a *parallel-process solution* has
material communication and CPU overhead. On these sub-second synthetic sources,
the overhead dominates. The R32i false positive also demonstrates why
identical timer instrumentation and delayed proof audits are required.

**Do not claim a general SAT breakthrough.** Before further parallel variants,
move to **genuinely difficult, externally sourced CNF formulas** with measured
baseline solve times of 1–120s, use uniform fair timers, include total core
and memory budgets, and compare certified single-process injection against
plain Kissat/CaDiCaL. For genuine intra-CDCL sharing, design a native
safe-point import that preserves the original search state and validates
all shared clauses; the current third-worker architecture does not do that.
