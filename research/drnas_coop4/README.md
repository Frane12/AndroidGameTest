# DRNAS COOP4 — how long should certified algebra knowledge survive?

Research status: experimental, no main changes, no blind holdout, no automatic promotion.

## Hypothesis

COOP3's immediate-propagation gate was too aggressive. In 42 stress synthetic CNFs,
COOP3_ALGEBRA solved 66/84, but COOP3_GATE only 63/84 and admitted just 14
clauses. COOP3 on retrospective SAT2024 REAL36 still failed to demonstrate
a statistically certified PAR2 gain. Our next question is not just WHEN to
learn, but WHEN to RETIRE short source-certified algebra consequences.

## Same-executable controls

All COOP4 candidates are compiled into the same original X5-derived CDCL
executable. The SAT/UNSAT proof system is not replaced.

- OFF: no affine analysis.
- ALGEBRA: COOP3-style certified affine knowledge, existing CDCL policy.
- KEEP: same lemma admission as ALGEBRA, instrument usage, never expire.
- SHORT: same admission, expire after 128 native conflicts without use.
- LONG: same admission, expire after 1024 conflicts without use.
- ADAPT: same admission; expire after 128 idle conflicts if never reused,
  after 1024 if reused once, or after 4096 if reused >=2 times.

Only the retention policy differs among KEEP/SHORT/LONG/ADAPT. Unit/conflict
lemmas and guarded binary XOR relations are all eligible. A learned clause
cannot expire if it is currently referenced by any assigned variable as
its reason. Expiry is checked only every 64 native conflicts, not in
the middle of unit propagation.

For expiring binary clauses, both binary implication edges are removed.
For long clauses, stale watchers skip deleted clauses, with compaction
during ordinary CDCL garbage collection. Remapping also updates tracked
clause IDs. The original proof log is NOT deleted or rewritten: previously
certified additions remain valid proof steps, and all UNSAT outcomes must
pass independent DRAT verification.

## How utility is measured

Record the conflict-age when an added clause is first used after insertion
as a propagation reason or in 1-UIP conflict analysis, its future reuse
count, idle age since last use, whether it was locked at expiry time,
and whether it was safely retired and later recertified.

The initial assertion of a lemma is excluded from the FUTURE-REUSE count.
The 'benefit' inferred from any one use is only a causal proxy: an
independent randomized paired run is needed to claim lower conflicts/PAR2.

We deliberately measure both first-use latency and survival. A candidate
that is not useful in its first 128 conflicts may still become useful
later, which is precisely why KEEP and LONG remain separate controls.

## Verification protocol

Preflight:
- compile generated C++20 solver under -O3 -Werror, enforce unchanged frozen
  X5 source Git blob identity;
- 256 exhaustive Boolean truth functions on three variables plus 180 random
  CNFs and targeted affine/nonlinear cases, with SAT oracle and independent
  RUP verification of each proof step;
- independent DRAT for all reported UNSAT; fast-path proof tests;
- reject malformed CNF or invalid refutation.

Benchmark:
- original SHA-frozen SAT Competition 2024 REAL36: 36 unique CNFs, 7 families,
  2 repetitions, 5s cap, nine arms = 648 paired trials;
- separate 42-case, 7-family stress synthetic, 2 repetitions, 1s cap,
  seven arms = 588 paired trials;
- each solver pinned to one logical CPU, randomized order within each formula,
  original CNF SAT witness validation, independent DRAT UNSAT certification;
- report verified PAR2, solved count, maxRSS, first-use and reuse/expiry
  frequencies, family-cluster paired confidence intervals.
- these are retrospective development sources and synthetic mechanism tests,
  not fresh blind evidence.

The criteria to promote remain: no incorrect SAT/UNSAT; statistically credible
reproducible performance improvement on never-tested family-disjoint real
holdout, and no solved regression. None of these policies are promoted by
the current experiment.
