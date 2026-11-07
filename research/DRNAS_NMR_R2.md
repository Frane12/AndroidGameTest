# DRNAS New Horizon — Neural Mixing Resolution R2

**Research status:** first experimental implementation. No claim of universal or statistically validated SAT speedup.

## Human-guided, online, persistent architecture

DRNAS NMR implements a small actual multilayer perceptron (10 inputs -> 8 tanh neurons -> 1 sigmoid output) and an interactive CaDiCaL 2.1 bridge. The neural controller samples **solver telemetry after bounded conflict windows**, rather than continuously sampling every CPU instruction. The human specifies goals, safety constraints and evaluation criteria; the model estimates strategy utility using an online, imperfect learning signal.

Code:
- `research/nmr_live_driver.cpp`: two independent, identical-source CaDiCaL configurations, interactive `STEP arm budget` and `FINISH arm` commands. Winning solver **continues in the same process** with its existing learned clauses.
- `research/nmr_online.py`: 10-feature source+dynamic vector; 10x8x1 MLP with SGD; adaptive conflict-window resolution; recurrence forecasting on quantized learning statistics; SQLite persistent checkpoint and per-formula learning episodes.
- `research/nmr_r2_benchmark.py`: deterministic SHA-disjoint train/test split, trained versus frozen versus live versus no-period versus shadow versus clean; paired audit with PAR2.
- `.github/workflows/drnas-nmr-r2.yml`: pinned CaDiCaL build, checksum verification, train-only checkpoint, GitHub Actions cache restored across successful executions, four evaluation shards and final audit artifact.

## What is learned

The input includes only:
1. number of source-certified XOR3 groups (capped);
2. XOR–residual CNF overlap;
3. fraction of binary clauses;
4. fraction of Horn clauses;
5. difference in short learned clause yield;
6. relative learned-clause offer rate;
7. relative window runtime;
8. mean learned clause size difference;
9. validated event-pattern recurrence confidence;
10. detected recurrence lag.

No case name, source SHA, family label, or expected SAT/UNSAT answer is passed to the policy.

After each **paired equal-budget** `default` and `sat` sample, the learner obtains a proxy comparison of short-clause yield and runtime, adjusts the network weights, and may select one surviving solver. Neither the proxy nor the learned neural output certifies that the chosen solver is globally optimal.

**Resolution**: the controller adapts conflict-window lengths (64/128/256) to live measurements. It learns at observation boundaries; do not claim per-instruction, every-CPU-cycle, or general-purpose real-time guarantees.

**Recurrence**: a non-constant quantized event signature must repeat three cycles (lags 2/3/4) and predict later samples before earning confirmed hits. Random or constant sequences are negative controls. This is telemetry recurrence, **not proof of underlying CNF periodicity**.

## Memory

`nmr_r2/model.sqlite` contains the MLP weights and episode counters, committed transactionally. The model reloads the same state on restart. GitHub Actions restores and saves this SQLite file with `actions/cache`; the run also uploads a memory artifact for audit. On local machines provide a persistent path to the model file. Standard ephemeral CI runners do not otherwise retain local files.

Training writes this file **only** with training formulas; evaluation loads it read-only. During `live` evaluation a private in-memory copy of the network continues to update inside the formula but is discarded afterward: this prevents evaluation cases from contaminating later held-out measurements. `frozen` switches without within-formula updates, `no_period` removes recurrence features, and `shadow` measures inference/probe overhead while continuing with default CaDiCaL. `clean` runs clean CaDiCaL directly.

## Truthfulness and proof

SAT witnesses are checked against the original, unmodified CNF. The controller never injects unsupported clauses. UNSAT results from native CaDiCaL are not independently LRAT-certified by this benchmark.

The same full time cap includes source scanning, subprocess creation, two-solver probe work, neural updates, and final solver work. Benchmark sources are R1 SHA-frozen originals and known synthetic families; the training/test partition is **source-disjoint but not generator-family-blind**. This is a methodological pilot, not evidence of new worst-case complexity guarantees.

## Audit criteria for progress

Measure solved/PAR2, matched wins/losses, full walltime, overhead, number of online updates, memory restored between executions, and out-of-sample recurrence forecasts. A gain is meaningful only if independent reruns preserve it and no unacceptable regressions or answer errors appear. Use new unseen SAT competition and industrial sources before making broader claims.

Reference baseline: DRNAS New Horizon R1 success, GitHub Actions run 42320433991. R2 workflow runs on `experiment/drnas-new-horizon-nmr-r2-20261107`.
