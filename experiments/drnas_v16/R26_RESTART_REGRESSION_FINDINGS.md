# DRNAS SAT R26 — confirmed R24 restart regression ablation
Date: 2026-11-03
Run: https://github.com/Frane12/AndroidGameTest/actions/runs/41606817712
Artifact: https://github.com/Frane12/AndroidGameTest/actions/runs/41606817712/artifacts/13216194408

## Scope and provenance
- Same R24-instrumented, SHA-pinned native Kissat executable across all four modes.
- Only source extension: permit delayed \`r11_4096_50\` via exactly one whitelisted condition; no changes to solver search policy in existing modes.
- Four independently SHA-verified original R24 fresh formulas: random3_test_00, _01, _02, _05.
- Three repeats, modes shuffled per case, single CPU affinity, 2.0 s cap, 48 executed attempts.
- All 48 trials completed (no timeouts); SAT witnesses checked on original clauses; no independently checked UNSAT certificates.
- These CNFs were inspected in R24: **diagnostic replays, not a new blind holdout**.
- The run successfully verified matching pre-2048 R6 checkpoints across arms.

## Median wall / PAR-2 times in seconds

| CNF | monitor | native switch @2048→25 | native switch @2048→50 | delayed @4096→50 |
|---|---:|---:|---:|---:|
| random3_test_00 (UNSAT) | 1.479610 | 1.216356 | 1.825343 | 1.252206 |
| random3_test_01 (SAT; main regression) | 0.057532 | 0.056505 | 0.176460 | 0.057156 (never switched) |
| random3_test_02 (UNSAT) | 1.126778 | 1.582210 | 1.028542 | 1.502085 |
| random3_test_05 (SAT) | 0.651750 | 0.064355 | 0.314540 | 0.260187 |

## Target interpretation: random3_test_01
- At checkpoint conflict 2048, monitor logged 3 restarts, 2,615 decisions, 78,484 propagations, 2,044 learned and stable=0.
- Monitor / 2048→25 / 4096→50 all solved SAT before 4096 conflicts.
- The 2048→50 path was still searching at conflict 8192: 24 restarts, 10,356 decisions, 357,915 propagations, 8,180 learned, stable=1.
- The extra exploration occurred after exactly matched early conflict telemetry. Triggering restartint=50 at 2048 is a reproducible causal lever for this regression.
- These measurements do **not** identify which clause(s), decisions or implication edges are responsible for the large path change.

## No universal policy fix yet
- Setting interval 25 at conflict 2048 drastically helps random3_test_05 but slows random3_test_02 (~40%).
- The original 2048→50 action helps random3_test_02 and random3_test_05, but harms random3_test_01 and random3_test_00.
- Delaying 50 until 4096 avoids the loss on random3_test_01 by never triggering, but also slows random3_test_02 in these matched trials.
- Therefore no single restart interval or timing should be promoted as a general-purpose fix based on these four known formulas.

## Next controlled hypothesis
Instrument post-2048 rates of restarts, conflict-derived clause reuse (LBD/age), propagations and decision-level breadth. Compare paired helpful vs harmful cases with a predeclared predictor that has a strict abstention/fallback and measurement cost included. Freeze on development and verify on new SHA-distinct blind formulas. Keep v15.3.1 unchanged.
