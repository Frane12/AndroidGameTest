# DRNAS R196 — causal split256 investigation

## Background
R195 (Actions 42332923725) completed 518 paired trials on 37 real CNFs. Split256 solved 5/74 vs default 4/74, PAR2 4792.616 vs 4853.157 s. That difference is dominated by a small number of cases and is not a general speedup claim.

## Hypothesis
Stopping a CDCL solver after 256 conflicts and calling solve() again can alter its trajectory. Which intervention matters? Mere limit bookkeeping; reentering solve(); the cutoff size; retained state; or statistics instrumentation?

## Precommitted seven arms
- default: uninterrupted native CaDiCaL 2.1.
- limit_cancel: set conflicts limit to 256, reset it to -1 *before* a single solve; no bounded interruption.
- split128_twice: two successive 128-conflict bounded solve calls, then continue same solver.
- split256: one bounded 256-conflict call, continue same solver.
- split512: one bounded 512-conflict call, continue same solver.
- split256_rebuild: run bounded 256, delete original solver, start a fresh solver from identical original CNF and same seed; explicitly discard *all* state.
- split256_trace: same split256 algorithm with statistics() at pilot boundary to quantify observer overhead.

Solver::statistics() reports native conflicts, decisions, propagations, and restarts. Active variables and redundant/irredundant clause counts are recorded at the pilot and end. Native statistics calls are charged to the benchmark wall-clock.

## Frozen sources and validation
- Eight original R195 formulas: four cases with known striking contrasts and four deterministic SHA-ordered negative controls.
- Four seeds (11, 23, 37, 47), seven paired modes: **224 attempted runs across eight shards**.
- All modes: original SHA-frozen CNF, identical seed and CaDiCaL 2.1 commit 31f9aae44947c673dc6190c9beb399acb9ffec6a.
- Historical original source manifest SHA caae5fe7abde52e3d886add24bf23cd925411504e9c866dddcbd2fc8cb595be4.
- 45-second caps, all processing counted, PAR2 timeout penalty 90 seconds.
- Every SAT witness checked against original CNF; native UNSAT not independently certified with LRAT/FRAT.
- Exact source SHA, seed and seven arms per pair enforced by fail-closed audit.
- Previously seen R195 cases: **not a blind independent real SAT holdout**.

## What we can conclude
If limit_cancel matches default but split256 diverges repeatedly, the limit-setting operation itself is unlikely to explain the effect. If rebuild loses the benefit, preserved *combined state* matters; learned clauses are only one possible cause. If two 128-call windows differ from a single 256-call window, interruption scheduling matters. If trace differs from split256, diagnostics perturb performance.

These are experimentally testable mechanisms, **not predetermined findings**. A phase-2 externally unseen CNF holdout is required before any deployment or universal speed claim.

Files: research/r196_split_causality_driver.cpp, research/r196_split_causality_benchmark.py, .github/workflows/drnas-r196-split-causality.yml.
