# DRNAS R7 wide benchmark

Frozen hypothesis: R7 gates a one-time `restartint=25` change at conflict
2048 if its 512-conflict cumulative-propagation metric is strictly between
0 and 35. The threshold was selected using earlier development data. The
gate is unchanged for this benchmark.

This benchmark uses no preselection based on monitoring or outcomes: 40
freshly generated random 3-SAT problems, 20 generated planted graph-coloring
problems, 20 generated cubic-graph parity problems, and 20 public SATLIB
problems (10 flat125, 10 AIM). Each is tested on one category runner with
original pinned Kissat, instrumented Kissat monitor, forced restart, R7, and
unchanged V15.3.1, in shuffled order, three repetitions, and an 8-second cap.
This yields 1,500 attempted runs. Generated cases are checked against a
snapshot of earlier normalized CNF SHA256 values and against each other;
the SATLIB collection is public and not claimed as unseen. This does not
establish novelty against every historical dataset.

The primary controlled comparison is R7 vs the same instrumented monitor;
also report original uninstrumented Kissat separately. Compare results per
formula with repeated runs rather than treating the repetitions as separate
formulas. Report per-category solved counts, timeouts, total PAR-2, intervention
frequency, median per-formula effects, and large regressions. The wall-clock
timer includes each solver's launch and any instrumentation. The R7 signal
uses the inherited cumulative propagation counter, potentially including
pre-search work; structure metrics are logged outside timed runs only.

SAT witnesses are checked against the formula. UNSAT results of Kissat are
not independently certified by this harness. This is not an official SAT
competition or a basis for claims of broad safety or world records.
