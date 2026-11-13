# DRNAS X5.5 — sampled thread CPU / watched-literal propagation profiling

**Scope:** research experiment only. The frozen X5.4 solver is unchanged and
the repository's \`main\` branch is not modified.

**Motivation.** X5.4 reduced the number of scanned nonwatched literals by
36.1% on the original REAL36 SAT2024 retrospective test but did not produce
a statistically significant reduction in end-to-end PAR2. Operation counts
cannot reveal time, I/O, memory stalls or profiler overhead.

## What is measured

The optional \`--x55-profile\` flag on \`src/drnas_x55.cpp\` samples CPU
time using Linux \`CLOCK_THREAD_CPUTIME_ID\`. This clock measures the
current thread's scheduled CPU time; it is not a hardware cycle counter,
memory-cache-miss counter, or wall-clock measure.

* Every 1024th propagated trail element: record CPU nanoseconds spent in
  **binary implication traversal** and in **watched-list scanning**. The
  sampled timer uses RAII so early returns on conflict, timeout or
  inspection budget retain the sampled duration.
* Every 128th invocation of conflict analysis, variable selection,
  reduction, proof-write and garbage collection: CPU timing bucket.
* \`X55_PROFILE\` emits sample counts and raw nanoseconds when a solver
  finishes. \`X55_PROGRESS\` preserves bounded partial samples on timeouts.
* Some profiling buckets (e.g. garbage collection inside reduction) are
  nested. Never sum all phase times as independent components.
* Multiplying sampled nanoseconds by the stride gives a **systematic
  sampling estimate**, not a precise full-run duration. Estimates may be
  noisy for short solves with few samples.

The benchmark also measures total external process user+system CPU, wall
time, maxRSS, proof size, independently verified SAT/UNSAT, and total PAR2.

## Comparison design

Six arms built with identical \`g++ -O3 -DNDEBUG -g
-fno-omit-frame-pointer\` flags:

| Arm | Binary | Cursor | CPU sampling |
|---|---|---|---|
| X54_CONTROL | frozen X5.4 | off | off |
| X54_ROTATE | frozen X5.4 | on | off |
| X55_CONTROL_OFF | X5.5 | off | off |
| X55_CONTROL_ON | X5.5 | off | on |
| X55_ROTATE_OFF | X5.5 | on | off |
| X55_ROTATE_ON | X5.5 | on | on |

This separates recompilation effects, profiling overhead and watch rotation.
All arms use the same X5.3 baseline deletion policy, clause-learning,
search heuristics and proof generation. The profiles are observational;
there is no learning, promotion or tuning in this run.

36 original real SAT2024 application CNFs from the SHA-frozen REAL36
manifest, two repeats each, cap 10 seconds and PAR2 penalty 20 seconds.
Total = 36 × 2 × 6 = 432 attempts, paired by original SHA and repeat,
one logical CPU at a time per solver. All SAT answers are checked against
the source CNF; UNSAT is counted only with independent DRAT certification.
Proof checker runtime is separate from solver E2E; proof writing remains
inside each solver's E2E.

The result is retrospective, **not a new blind holdout**. Formula-cluster
bootstrap treats repeats as dependent, not independent observations.

## Optional hardware perf counters

A separate observational job tries \`perf stat\` for CPU cycles,
instructions, cache misses and branches on an unchanged original
hardware-miter source. GitHub-hosted runners may deny \`perf_event_open\`.
If unavailable, the artifacts state that explicitly: **do not infer a
zero cache-miss count**.

## Quality gates

The CI smoke test uses 55 generated small/analytic SAT/UNSAT instances,
a brute-force oracle for the small subset, and independent DRAT checks on
all UNSAT cases. Control/rotation runs are also checked for matching
decision, conflict, propagation and reduction counts when profiling is
toggled. The actual real36 benchmark is then executed separately; no
gain is claimed from smoke tests alone.

If the 512 MiB proof resource cap is hit, the result is censored as
\`PROOF_SIZE_LIMIT\`, not a wrong SAT answer. Neither status nor sample
count is silently converted into a successful solve.

**Success criterion:** time saved in watched-list CPU, not only fewer
literal scans; profiler overhead small; verified source-paired PAR2
improvement on a distinct held-out real set, with acceptable RSS.
Do not promote based on retrospective REAL36 alone.

Run:
https://github.com/Frane12/AndroidGameTest/actions/runs/43404857394
