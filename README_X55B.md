# DRNAS X5.5b — corrected CPU profiler

**Experimental branch only:** `experiment/drnas-x55b-batched-bcp-20261113`. No main changes.

The preceding X5.5 run sampled *individual propagated trail elements* using
Linux `CLOCK_THREAD_CPUTIME_ID` every 1024 elements. On the first
nontrivial original SAT2024 shard, extrapolating sampled nanoseconds with this
ratio yielded CPU estimates larger than the entire measured process CPU. The
three clock calls, even when made only on sampled elements, contaminated
each extremely short sample. **Those extrapolations must not be treated
as actual BCP CPU time.**

X5.5b repairs this design by sampling **complete nonempty
`propagate()` invocations** instead, every 64th invocation,
using only two thread CPU timestamps per sampled invocation (entry / RAII
exit). A finished call includes its binary implication traversal,
watched-list traversal, and the normal internal exit path on conflicts or
timeout. It does not try to apportion sub-microsecond costs to individual
trail elements. Timer overhead should therefore be smaller relative to the
sampled work.

Other optional phase samples (conflict analysis, proof I/O, select,
reduction, GC) are still short-duration samples and are **only supporting
diagnostics**, not additive ground-truth CPU partitions. The report flags
any batch extrapolation that exceeds 125% of total measured process CPU
as implausible rather than silently claiming a speed measurement.

## Frozen small retrospective test

- 12 original SHA-verified SAT Competition 2024 real-world CNFs selected
  by source `id % 3 == 0` from the previously frozen REAL36
  source manifest, with no runtime/outcome screening.
- Two paired repeats and five arms (120 total trials), eight-second
  solve E2E cap, independent SAT-model / UNSAT-DRAT verification.
- Uninstrumented frozen X5.4 CONTROL and ROTATE; same-branch rebuilt
  X5.5b CONTROL without profiling; CONTROL and ROTATE with coarse
  CPU instrumentation.
- One logical CPU per solver and 512 MiB proof-size limit.
- The independent exact-oracle smoke test verifies equal decisions,
  conflicts, learned-clause counts, propagations, and reductions on
  unprofiled/profiled controls. **No change to search correctness or
  solver learning policy is intended.**

## Reporting standard

The **primary speed metric** is externally measured process user+system
CPU and solve wall time / PAR2 with profiling disabled. The sampled
`propagate()` CPU estimates are secondary and must
be validated for plausibility on the original formulas. Proof-check
time is reported separately.

Even a plausible reduced BCP CPU estimate alone is insufficient to
claim solver speedup: same-original paired PAR2, verifier correctness
and RSS remain independent success criteria.

X5.5b CI: https://github.com/Frane12/AndroidGameTest/actions/runs/43406104528

X5.5 full REAL36 control (external CPU still valid, fine-grained
BCP extrapolation not valid):
https://github.com/Frane12/AndroidGameTest/actions/runs/43404857394
