# DRNAS SAT v9.0 — actual first-UIP LBD, propagation, backjump telemetry

Experiment: https://github.com/Frane12/AndroidGameTest/actions/runs/41228543887
Date: 2026-10-31

## Method
CaDiCaL 3.0.1 pinned at c60730422e758ef1cebe7aeddf2dda31c996bf04; patch_cadical_v90.py instruments only a throwaway clone on the runner, not the original upstream or frozen DRNAS v7.6/v7.7 source.
Actual first-UIP pre-minimization glue/LBD and LBD<=2, LBD<=4 are counted in analyze.cpp. Search propagations come from the upstream stats.propagations.search; actual backjump depth is counted at determine_actual_backtrack_level. Only a separate instrumented Solver::drnas_telemetry() exposes checkpoints.
All five modes link against the same instrumented library. v9.0 observes but DOES NOT make decisions from the quality counters; its 256-conflict learned-delta gate and optional 768-conflict extension replicate original v7.6. Instrumentation adds conflict-analysis overhead, so no low-level speedup is proven.

## Prospective test
30 fresh seeded synthetic CNFs, 5 families, 5 modes, 3 repeats = 450 attempts. One CPU per runner shard. 3s cap, PAR2=6s timeout; all failures accounted for.
Sum of per-CNF PAR2 medians (lower is better):
- v90_quality_no_hints: 48.38072 seconds
- orig_v76_plain: 48.39269 seconds
- ca_plain: 49.05288 seconds
- v90_quality_guided: 49.29509 seconds
- orig_v76: 49.33128 seconds
Matching instrumented original and diagnostic branches have similar aggregate timing. No solver answer contradictions detected, but no independently verified UNSAT certificates.

## Exploratory 256-conflict signal
For the 16 formulas solved in all 3 repeats by both guided/no-hint modes, with unhinted baseline at least 0.05s:
- Spearman(LBD<=2 fraction vs log speedup of guided over no-hint): +0.363.
- Spearman(search propagations per conflict vs log speedup): +0.315.
- Spearman(mean actual backjump depth vs log speedup): -0.144.
These are uncorrected exploratory correlations on a small and selected sample, not prospective predictors.

Examples:
- color3-410: guided 0.0753s vs no-hints 0.1949s = 2.59x; 6.0% LBD<=2.
- random3-228: guided 0.1675s vs no-hints 0.4823s = 2.88x; 6.1% LBD<=2.
- random3-240: guided 0.4299s vs no-hints 0.2146s = 0.50x; 2.8% LBD<=2.
- random4-115: guided 1.6317s vs no-hints 0.5340s = 0.33x; 1.2% LBD<=2.
- Counterexample color3-350: guided 0.5469s vs no-hints 0.5023s = 0.92x despite 11.7% LBD<=2.

## Engineering/science decision
Frozen v7.6 remains stable; v9.0 is diagnostics only, no speed record. True LBD here is not the clause length exported by a public Learner. Read counters after the first 256 conflicts, with one solver instance throughout.
To test causally whether quality metrics can decide phase use, keep the FIRST 256 conflicts IDENTICAL and unhinted for matched policies, then select late hints based on frozen prespecified thresholds. Never treat post-256 LBD values as predicting benefits from hints already present during the initial 256-conflict segment.
Next benchmark must be genuinely fresh, with fixed criteria, timeout penalties, real SAT correctness and independent UNSAT proof checks. No P=NP, world record, or universal solver advantage established.
