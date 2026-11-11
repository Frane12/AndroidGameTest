# DRNAS ATLAS27 — Conditional C7 Reason Reuse and BCP Pressure
2026-11-11

## Why
ATLAS26's C26_REUSE3K won materially over C7 on a nonblind 10-SHA
regression cohort (verified PAR2 169.28 vs 203.54 seconds; E2E 44.71 vs
68.15 seconds), but regressed on a separate 6-SHA extension cohort
(152.05 vs 134.56 verified PAR2, and 6 vs 7 verified SAT trials).
Always-on reason-reuse scoring therefore does **not** warrant promotion.

## Frozen prospective hypothesis
Instrument real native CDCL reason use as in ATLAS26, but apply its
bounded deletion-candidate score discount **only** when the live,
within-solver 1500-conflict samples show:

- BCP watch visits >= 12 × propagations;
- >= 32 actual propagations in window;
- >= 32 newly registered learned-clause reason uses;
- >= 16 repeated reason uses, with repeated reasons accounting for at
  least one-quarter of all reason uses.

Two consecutive qualifying windows activate the policy. Two consecutive
non-qualifying windows deactivate it. Scores stay bounded: only the
existing ATLAS26 score discount is activated; no learned clause is
categorically immune to C7's deletion quota. New modes use a 3,000- or
6,000-conflict recent-use window independently.

This does **not** mutate SAT/UNSAT inference or overwrite C7/C26 modes,
does not use class names, labels, solver verdicts or hashes for gating,
and does not carry train/test decisions from one SHA into another.

## Experimental arms
`A`, `C7_ADAPT`, `C7_ADAPT_GAUSS`,
`C26_REUSE3K`, `C26_REUSE6K`,
`C26_REUSE6K_GF2`, `C27_GATE3K`,
`C27_GATE6K`, `KISSAT`, `CMS`.

One process and one logical CPU per matched trial. No parallel
portfolio. Kissat built from the same pinned source revision as ATLAS26;
CMS is single-threaded.

## Cohorts
- 10 historical SATLIB regression SHA (nonblind, cap 10s)
- 6 historical SATLIB extension SHA (nonblind, cap 12s)
- 10 source-pinned SATLIB SHA at archive indices 12/13 across 5 source
  families (prospective relative to ATLAS26 cohorts; cannot assert global
  blind status, cap 12s)
- 30 deterministic synthetic SHA at indices 180/181 across 15 families
  (prospective relative to ATLAS26 cohorts, cap 8s), four shards.

56 unique original SHA x 10 arms x 2 repetitions = 1,120
matched attempts, separate per-source and per-shard summaries.

SAT must pass original CNF model verification; UNSAT gains verified
PAR2 credit only after independent original-CNF source-GF2 contradiction
verification. Kissat/CMS UNSAT without independently checked proof is
reported as unverified; no claim of certified UNSAT. End-to-end runtime,
CPU, watch visits, propagations, clause deletion, LBD and allocated
clause memory are logged. No thresholds changed after evaluating tests.

## Interpretation
Primary experimental comparison is C27_GATE3K and C27_GATE6K against
C7 and C26 on the new source cohort, with identical caps/seeds.
The former may legitimately abstain from using the bonus and remain
functionally identical to C7 for low-pressure cases; gate activations,
score-eligible candidate counts and bypass counts prove whether it
really engaged. Improvement on a recycled SHA is diagnostic only.

SQLite `event` rows are `trial_completed`, not a log of
individual CDCL decisions or proof of online learning. Use
`ATLAS27_AUDIT` and `ATLAS27_SQL` before claiming any final result.

Experiment branch only. Never modify stable main, frozen controls,
pre-existing CNF files, certificates or completed benchmark archives.
