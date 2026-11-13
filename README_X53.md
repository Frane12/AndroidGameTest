# DRNAS X5.3 — Clause Utility + Watched-BCP Audit

**Status:** experimental branch only. Neither `main` nor any frozen
reference solver has been modified.

## Hypothesis

The original FAMILY15 diagnostic on 75 SAT Competition 2024 instances showed
heavy CDCL work with many learned clauses discarded and BCP occupying
approximately 60% of observed solver time. This does **not** establish that
deletion caused the timeouts: preserving low-value clauses can *increase*
watched-literal scanning work. X5.3 measures the relationship.

## Three frozen policies

All X5.3 arms use the same X5.2 parser, 1-UIP, propagation, minimization,
restarts, watcher implementation and proof generation.

* `--x53-policy baseline`: exactly the existing X5.2 retention selection,
  with observer-only counters.
* `--x53-policy glue`: protect learned clauses with LBD <= 3; prefer deleting
  high-LBD eligible learned clauses, 50% at each qualifying reduction.
* `--x53-policy utility`: protect LBD <= 4, clauses used within the past
  2048 conflicts and clauses with at least three real reason/analysis/conflict
  uses if LBD <= 8; reduce one-third of other eligible learned clauses.

All policies preserve binary clauses and currently locked reason clauses.
There is **no online tuning or per-formula memo**. Counters exclude speculative
X4.6 clones and bounded probes. `--x53-progress` emits periodic small
snapshots for timed-out solves without creating a persistent clause database.

## Instrumentation

The `X53_STATS` line reports:

- BCP trail pops, binary implication checks, watched-list entries, deleted
  entries encountered, satisfied blockers, scanned extra literals, watch moves,
  unit events and conflicts.
- Per learned clause: times used to imply a literal, during 1-UIP conflict
  analysis, or as the cause of a propagation conflict.
- Counts of deleted clauses never used vs previously used; their LBD buckets;
  protection reasons (LBD/recency/reuse); surviving learned counts by LBD
  and measured use. **Use count is not proven usefulness in runtime savings.**
- `X53_PROGRESS` is censored at the last flush when a watchdog kills a
  process. Missing counters on a timeout must not be treated as zero.

An independent unchanged X5.2 binary provides an instrumentation-overhead
control. The 44-instance small SAT/UNSAT exact-oracle test checks 176 runs,
including independently checked DRAT certificates and **identical decision,
conflict and propagation counts** between X5.2 and X5.3 BASE.

## Paired real benchmark

Source: 36 original, SHA-frozen SAT Competition 2024 application CNFs from
REAL36 STRICT, unchanged, two repeats per instance, six arms, cap 8 seconds.
Arms: X52_BASE, X53_BASE, X53_GLUE, X53_UTILITY, Kissat and CaDiCaL.
Total: 36 × 2 × 6 = **432** executions, distributed over 12 shard jobs
with one logical CPU per solver run.

All solvers pay their proof-write costs in solve E2E. SAT witnesses are checked
against the original formula. UNSAT is credited **only** if a proof is checked
independently with `drat-trim`, and that audit cost is reported separately.
PAR2 = measured solve E2E for a certified finish within the 8-second cap,
else 16 seconds. Both repeats are one source-cluster for uncertainty analysis.

The benchmark is **retrospective on a size-selected original SAT2024 set**,
not a new blind holdout. No automatic promotion. For a production claim,
require further independently selected real formulas, a verified improvement
in source-cluster PAR2, no certified correctness failures, and no unacceptable
regression in maxRSS or in previously solved cases.

## Run

[GitHub Actions X5.3](https://github.com/Frane12/AndroidGameTest/actions/runs/43399730112)

The workflow restores archived original input bytes and reference binaries,
checks SHA, compiles X5.2 and X5.3 using identical flags, runs exact-oracle
tests, freezes the metadata, then runs the paired benchmark. All evaluation
and reporting code resides in `research/drnas_x53_real36.py`.
