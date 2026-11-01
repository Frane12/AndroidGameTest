# DRNAS R7: experimental early-propagation gate

## Hypothesis and intervention

This is an exploratory, R6-informed threshold, not a validated optimum. On the
same pinned Kissat source as R6, at the first 512 conflicts, permit a one-time
change of `restartint` to 25 at 2048 conflicts only if the reported early
propagation value is positive and strictly below 35. When the checkpoint is not
reached, or the value is outside that interval, the gate abstains. The gate
does not restart the solver, alter the clauses, or reset learned state.

The value exactly follows the existing V17.7/R6 definition: cumulative Kissat
propagations at the 512-conflict checkpoint divided by 512. It may include
propagations from before the main search; it is not a pure windowed derivative.
The number 35 was chosen after inspecting R6 and must not be reported as a
pre-registered threshold on R6 or a proven safety boundary.

## Comparison and input identity

Four interleaved modes per formula on one runner: unchanged V15.3.1; the R6
instrumented monitor; the same instrumented Kissat with a forced change at 2048;
and the experimental R7 gate. Monitor versus R7 or forced is the controlled
comparison; V15.3.1 uses a distinct architecture and serves as a reference.
Each mode is run three times, with an 8-second cap, on 10 generated random
3-SAT, 10 planted graph-coloring, 10 cubic XOR and 10 previously public SATLIB
controls. Random generators and seeds are changed from R6. Generated normalized
CNF SHA256s are checked against the supplied historical database snapshot;
this supports novelty only relative to that snapshot, not all historical runs.
External SATLIB controls are previously seen and are not claimed as a holdout.

Record actual gate eligibility, whether intervention occurred, raw timing,
status, solver counters and traces, CNF SHA256, runner, source commit, and
source/executable fingerprints. Formula-level degree Gini and CV are recorded
for offline analysis only; they do not affect the solver or measured time.
Report solved counts, PAR-2, per-formula effects and severe regressions. Treat
repetitions as repeated measurements of the same formula, not independent cases.
SAT models are checked; Kissat UNSAT is not independently certified here.
Do not infer universal safety or competition standing from this small test.
