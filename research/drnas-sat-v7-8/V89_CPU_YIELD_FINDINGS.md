# DRNAS SAT v8.9: retained-clause yield per CPU time and conflict (2026-10-31)

## Implementation and controls
- Branch: experiment/drnas-sat-v89-yield-cpu-20261031.
- Probe: research/drnas-sat-v7-8/v89_yield_probe.cpp.
- CaDiCaL 3.0.1 and source-frozen DRNAS v7.6 and v7.7 are unchanged.
- A single solver retains its learned clauses across all stages. No hot-path learner callback in new v8.9.
- First 256 conflicts run without artificial phase hints. At this first boundary, the algorithm compares retained redundant-clause delta against the original durable threshold.
- For sufficiently strong progress, it preserves the full 768-conflict extension. Near-threshold instances may sample 128 additional conflicts and compare retained clauses per CPU nanosecond and per conflict budget; only then continue up to 640 additional conflicts. No new hardware instrumentation is inserted into propagation.
- v89_rate_no_hints and v89_rate_late_hints are matched ablations. The latter introduces phase hints only after the first 256-conflict stage; all models verified by C++, UNSAT proofs not independently verified.
- Public redundant() is a count of retained redundant clauses, *not* LBD, full learnt clause count, or an intrinsic usefulness score.

## Frozen 25-case prospective benchmark
Original run: https://github.com/Frane12/AndroidGameTest/actions/runs/41227731300
25 newly generated deterministic SAT CNFs in five families, 6 methods, 3 repeats = 450 solver runs. Each attempt capped at 3 s; a timeout contributes 6 s PAR2. Five independently hosted single-core shards and matched same-runner comparisons.

Sum of 25 per-case PAR2 medians (lower is better):
- orig_v76: **40.44950 s**
- delayed_v88b: 41.00178 s
- v89_rate_late_hints: 41.11622 s
- ca_plain: 42.16877 s
- orig_v76_plain: 43.22402 s
- v89_rate_no_hints: 43.25261 s

On this test, v8.9 with late hints is about 2.5% below ordinary CaDiCaL's total, but approximately 1.65% worse than the frozen original guided v7.6. The new no-hints gate also underperformed CaDiCaL. No general acceleration is established.

Family-level qualifying comparison (CaDiCaL median >=0.1 s, all 3 repeats solved, comparing v89_rate_no_hints):
- random3: 3 qualifying; median 0.951x; 0 wins >1.25x; 0 losses <0.8x.
- random4: 1 qualifying; median 0.647x; 0 wins; 1 regression.
- color3: 2 qualifying; median 0.920x; 0 wins; 0 regressions.
- xor3: 1 qualifying; median 0.766x; 0 wins; 1 regression.
- pigeonhole: 1 qualifying; median 1.147x; 0 wins; 0 regressions.

No contradictory SAT/UNSAT statuses detected. Some UNSAT instances were only mutually cross-checked, not proof certified.

## Verified hardware-counter limitation
Saved-hardware-artifact audit: https://github.com/Frane12/AndroidGameTest/actions/runs/41228063641

All five GitHub-hosted runners reported /proc/sys/kernel/perf_event_paranoid = 4.
perf stat attempts for ca_plain, v89_rate_no_hints, and v89_rate_late_hints were DENIED on each runner.
No reliable cycles, instruction counts, branch misses, or cache misses were collected.

C++ clock_gettime(CLOCK_PROCESS_CPUTIME_ID) recorded process CPU nanoseconds for v8.9 stage 256, optional stage 128, and total v8.9 solve; those are not hardware CPU cycles.

## Research decision
- Do not promote v8.9 as the default or world record; keep v7.6 frozen.
- No evidence that CPU-time/conflict-yield gating is a robust predictor of phase-hint usefulness.
- On hardware with perf counters available, separately measure retired instructions, cycles, L1/LLC misses, branches, and branch misses on sufficiently long instances (hundreds of milliseconds+). Prefer many paired repetitions and fixed CPU governor/cores.
- Improving training requires independent held-out CNFs and robust targets: method-specific total PAR2 or solving probability, not only short-term retained clause counts.
- A claim that a heuristic gives a general solver advantage, breaks P≠NP, or proves a complexity result is NOT supported by these experiments.
