# DRNAS v9.1 — causal first-256 checkpoint LBD/propagation gate (2026-10-31)

## Benchmark and source
Original 540-run experiment (all five solver shards passed; first aggregate failed only due to a CSV repeat str/int mismatch): https://github.com/Frane12/AndroidGameTest/actions/runs/41229157750
Corrected aggregate of SAME saved measurements, no solver reruns: https://github.com/Frane12/AndroidGameTest/actions/runs/41229544641
Final branch: experiment/drnas-sat-v91-aggregate-fix-20261031
All 30 distinct SHA256 CNFs preserved, 5 synthetic families, 3 paired repeats, six solver modes, single-core GitHub Actions shards, 3 s timeout and PAR2 penalty=6 s.

## Frozen method
- Pinned CaDiCaL 3.0.1 is patched ONLY in ephemeral runner copy for TRUE first-UIP LBD and propagations; original v7.6/v7.7 frozen files are not changed.
- All three new modes use the same initial 256 conflicts WITHOUT phase hints, same random seed, same 256 learned/active delta and same v7.6 768-conflict continuation decision. Telemetry is read at the checkpoint.
- Only difference is whether phase hints are applied AFTER the identical initial 256 conflicts: never, always on durable continuation, or only when quality gate passes.
- Frozen rule set BEFORE new holdout: at least 20 learned first-UIP clauses, at least 6% LBD<=2, and at least 32 search propagations per conflict.
- Verified exact equality of all available first-256 instrumentation in every fully observed paired triplet. Timeout attempts lacking complete output are excluded from equality audit but included as 6 s PAR2.

## PAR2 totals (sum of 30 medians), smaller is better
- orig_v76 guided from start: 41.16382 s
- ca_plain: 43.98028 s
- v91_always_late: 44.49893 s
- v91_quality_gate: 44.83498 s
- orig_v76_plain: 44.89876 s
- v91_never_late: 44.90942 s

Quality gate vs never-late: ~0.17% lower PAR2, not meaningful evidence of general gain. Quality gate vs always-late: ~0.76% higher PAR2. Quality gate vs CaDiCaL plain: ~1.94% higher PAR2. Guided v7.6 retains best aggregate on this holdout.

## Family accounting
- random3: 6 CNFs, 5 measurable, median never/selector 1.002x, 0 practical wins, 0 regressions, 3 of 15 known selector rounds with hints.
- random4: 6 CNFs, 3 measurable, median 1.001x, 0 wins or losses, 0 of 9 known selector rounds with hints.
- color3: 6 CNFs, 2 measurable, median 1.001x, 0 wins or losses, 6 of 18 known selector rounds with hints.
- xor3: 6 CNFs, 3 measurable, median 1.000x, 0 wins or losses, 3 of 18 known selector rounds with hints.
- pigeonhole: 6 CNFs, 2 measurable, median 0.999x, 0 wins or losses, 0 of 12 known selector rounds with hints. Pigeonhole problems are structurally isomorphic across relabelings despite distinct hashes.
Total known paired repeats with readable telemetry: 72; quality gate applied hints in 12. No SAT/UNSAT status contradictions detected; UNSAT proof certificates not independently checked.

## Implications
- There is a causal post-256 test, but no confirmed reliable performance advantage of the v9.1 quality gate.
- The old v7.6 initially guided search may gain from phase decisions BEFORE 256 conflicts, which a checkpoint-after-256 gate cannot retroactively recover.
- The v9.0 LBD correlation (+0.363 on only 16 selected solved instances) was exploratory and does not establish predictive power.
- Do not tune this rule on v9.1 cases and call these cases blind again. Any new gate needs a new pre-registered independent evaluation.
- Avoid publishing world-record/complexity-theory claims. Consider earlier-cost feature extraction, matched budget changes or prospective training of simple selectors, and independent hard SAT Competition instances with same platform, fixed budgets and proof validation.
