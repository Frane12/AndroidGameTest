# DRNAS SAT v9.2 — pre-first-conflict structural phase selector
Date: 2026-10-31

## Original and corrected audit
Original 540-run SAT workflow: https://github.com/Frane12/AndroidGameTest/actions/runs/41230152743
Successful aggregation of the SAME saved 540 results, without solver reruns: https://github.com/Frane12/AndroidGameTest/actions/runs/41230460498
Original final check failed only on an early-terminal-SAT parity condition: frozen v7.6 leaves learned_delta/threshold/active_256 at zero if stage1 already solved; v9.2 diagnostics record post-stage1 counters. Aggregate parity now compares these only if frozen v7.6 reached the 256-conflict decision. Source and experiment are not tuned after the test.

## Implementation
- v92_early_structural.cpp; O(total literal occurrences + number of variables) deterministic single scan before search. No family names, instance labels, SAT/UNSAT results, or downstream timing used.
- First-stage polarity candidates: >=6 occurrences and >=15% sign imbalance (broad). Strong subset: >=8 and >=30% imbalance.
- Width-heavy 4-clauses or 2-clause-dominant formulas containing a long clause are kept unhinted; sufficiently supported 3-clause and binary/short clause formulas receive broad majority hints; otherwise use a strong subset only if >=12.5% of variables or skip.
- Frozen original v7.6 256-conflict checkpoint, learned-delta threshold and optional 768 continuation are preserved; same single solver and learned database. A v92_full_compat control precisely tests parity against frozen v7.6.
- Same diagnostic CaDiCaL 3.0.1 instrumented clone for all methods, original frozen source files hash verified. The true-LBD telemetry from v9.0 remains observational, not part of this selector.

## Prospective matched test
30 distinct SHA256 CNFs, six synthetic families (random3/random4/color3/xor3/pigeonhole and newly introduced planted3 with SAT-by-construction witness), six modes, three repeats = 540 solver subprocesses. Five single-core GitHub Actions shards, 3 s per attempt and 6 s PAR2 timeout penalty.

Full sum of 30 per-case PAR2 medians, lower is better:
- orig_v76_plain (no hints): 29.01505 s — best
- v92_sparse (only strongly imbalanced phases): 29.22551 s
- v92_structural: 29.33219 s
- v92_full_compat: 31.00905 s
- orig_v76 (full initial phases): 31.01685 s
- ca_plain: 31.03062 s

v9.2 structural is ~5.47% lower total PAR2 than ca_plain and ~5.43% lower than orig_v76 guided on this finite set, but ~1.09% WORSE than orig_v76_plain. These small aggregates are descriptive, not statistically established generalized speedups.

Family-level eligible speedup (three runs solved by plain, guided and structural; both baselines >=0.05s):
- random3: n=4, median Ca/structural 0.977x; one >1.25x win, one <0.8x regression.
- random4: n=3, median 1.021x; one win, one regression.
- color3: n=2, median 0.815x; one regression.
- xor3: n=3, median 1.181x; one win, no regressions.
- pigeonhole: n=1, median 0.913x; no wins/losses.
- planted3: n=3, median 1.321x; two wins, one regression.

Concrete examples:
- random4-132: plain CaDiCaL 2.3558 s, guided v7.6 2.4677 s, v9.2 structural 0.5452 s, original v7.6 without hints 0.5470 s. Avoiding initial hints is beneficial, NOT a new fundamentally faster solver.
- planted3-230: v9.2 strong-only 0.1329 s vs guided v7.6 0.4122 s. A specific 3.10x instance speedup for sparse hints, not general across cases.
- planted3-190: plain CaDiCaL 0.0740 s, guided v7.6 and v9.2 structural ~0.196 s: a severe regression. This is a genuine newly introduced SAT-by-construction family; static majority hints cannot be generally assumed to help.

## Correctness, limitations, and next decision
All 540 attempts present; no reported solver errors or contradictory SAT/UNSAT statuses. SAT witnesses are checked by C++ per solved instance. UNSAT proofs have NOT been independently verified.
Full compatibility audit passed for all terminal solved matched pairs, comparing only frozen v7.6 counters meaningful for its actual state.
Pigeonhole formula permutations with distinct hashes are structurally isomorphic; synthetic generator families are not independent of earlier exploration. Only planted3 is a genuinely new family here. Do not call this a SAT Competition or world-record benchmark.
Decision: preserve original v7.6 as baseline. v9.2 static routing provides a falsifiable mechanism but does not beat the best no-hint v7.6 control. A next-stage predictor should be evaluated on previously unseen, independent harder problem distributions, with early overhead and proof validation, rather than tuned on these 30 and retested as if blind.
