# DRNAS SAT R7 large paired benchmark

Frozen R7 rule and solver binaries are unchanged from the R7 wide experiment.
At 512 conflicts the R7 gate considers the inherited propagation counter, and
if it is in (0,35) schedules restartint=25 at conflict 2048. No policy is tuned
on this benchmark.

## Data and comparisons

* 120 generated random 3-SAT formulas: 40 each of n=200, 220, and 240, density
  approximately 4.23 clauses/variable, fixed new seeds, no prescreening.
* 10 generated graph-coloring and 10 cubic parity/XOR formulas. The graph
  generator includes planted SAT and explicit K4 UNSAT cases; their difficulty
  is not representative of general graph coloring.
* 20 external SATLIB formulas: 10 flat125 graph-encoding instances and 10 AIM
  instances. These are public, can have been seen, and are not official 2026
  competition problems. Track source SHA and historical overlap.

5 modes: original pinned Kissat, the instrumented monitor, forced restart,
R7 gate, and unchanged V15.3.1. One formula is run 3 times per mode in shuffled
order on the same runner, with one selected CPU core pinned for all child
processes. Cap 12 seconds per attempt; timeout contributes 24 seconds to
PAR-2. This yields 160 x 5 x 3 = 2400 attempts. Separate shards use separate
hosted runners; no assumption of identical performance across shards.

The baseline for causal action comparison is the instrumented monitor on the
same binary. Original Kissat and V15.3.1 have different instrumentation or
architecture and are separate practical references. SAT models are validated;
Kissat UNSAT is not independently certified by this harness. No official
ranking or general safety claim follows from this experiment.

Generated formulas are checked against a 740-hash historical snapshot and
for cross-shard collisions; this does not rule out overlap with all other
historical data. Public SATLIB cases are labeled separately, not called
independent unseen data. Raw measurements, source and executable hashes, CPU
affinity, traces, status, PAR-2, formula comparisons, and partial shards are
retained as workflow artifacts. Compare formula-level paired results and report
timeouts, interventions and severe regressions, not only the total runtime.
