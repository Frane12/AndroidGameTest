# DRNAS V9.7 — risk-bounded predictive portfolio: preregistered protocol

Date: 2026-10-31

## Goal and critical caveat
Avoid V9.6's lost SAT solutions and large regressions by keeping a fully independent frozen V9.2 Sparse baseline running on a dedicated physical core in every portfolio attempt. The speculative candidate has its own CaDiCaL instance on another physical core. First validated solution wins, and the other process is terminated. If only one physical core is available, all portfolio modes fall back to Sparse baseline.

**Zero-regression cannot be guaranteed.** Process spawn overhead, OS scheduling, shared memory pressure and multicore allocation can delay the baseline. It spends up to two times CPU and memory, which must be reported. All modes have the same total wall time cap. CPU budgets are not equal; use caution when comparing with single solver.

## Frozen predictor
Reuse the fixed V9.6 structural formula model with no updates. V9.6 chooses Broad if its score is no greater than log(1.30), else Sparse. For the latter prediction, this portfolio speculates with plain CaDiCaL (Sparse is already running), otherwise with Broad. The prediction cost is included in runtime.

Baselines: plain CaDiCaL, V9.2 Sparse, V9.2 Structural (Broad), hedge-broad (Sparse + Broad), hedge-plain (Sparse + CaDiCaL), and guarded (Sparse + prediction-selected competitor).

Original frozen V7.6 / V9.2 sources unchanged.

## New holdout
Six previously unseen original SATLIB source members from each of four SAT/UNSAT RND3SAT 225/250 families = 24 CNFs, selected via fixed SHA256 salt drnas-v97-safe-hedge-20261031-frozen-v1. Entire 80-member previously CaDiCaL-screened list plus all 24 source members used in V9.6 are excluded. Disjoint formulas, but same SATLIB archives/families; NOT an external competition holdout.

3 repeats * 24 formulas * 6 modes = 432 paired attempts. Wrapper and feature time counted within a 4s wall-clock limit; timeout contributes 8s PAR2. Each concurrent solver is pinned to a different physical core. SAT models validated in C++; UNSAT relies on official SATLIB labels and solver agreement, not independent DRAT/LRAT.

Preregistered metrics: mean PAR2, solved count, paired wins >1.25x and losses <0.8x vs Sparse, maximum per-instance slowdown, candidate/winner choices, physical-core count, errors and resource cost.

Promotion only if lower PAR2 than best fixed baseline, no severe regression and CPU cost explicitly accepted. If negative, preserve Sparse and do not relabel tuned cases as blind.

## Recovered V9.6 audit
Run 41236688021 finished all 4 benchmark shards; its audit failed because it looked for manifest directly under each shard instead of shard/results. This workflow verifies the 288 immutable measurements without solver reruns.
