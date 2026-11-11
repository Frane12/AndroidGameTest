# DRNAS ATLAS26 — Real Reason Reuse + Source-GF(2) Proof-first, 2026-11-11

## Preregistered engineering hypothesis

The C7 learned-clause reduction scheduler is frozen. Its BCP pressure
sampling, fixed reduction quota, LBD thresholds, restart and branching
logic are not changed. We hypothesize that **measured recent reason use**
is a better deletion priority signal than LBD and length alone.

We compare:

| Arm | Frozen CDCL | Recent reason-use score | GF(2) |
| --- | --- | --- | --- |
| A | no (native A) | no | no |
| C7_ADAPT | yes | no | no |
| C7_ADAPT_GAUSS | yes | no | source-derived GF2 |
| C26_REUSE3K | yes | 3000-conflict window | no |
| C26_REUSE6K | yes | 6000-conflict window | no |
| C26_REUSE6K_GF2 | yes | 6000-conflict window | source-derived GF2 |
| KISSAT | pinned external solver | no | n/a |
| CMS | system CryptoMiniSat, one thread | no | native CMS implementation |

## Native implementation

- New C26-only per-learned-clause map keyed by clause ID; tracks saturating
  16-bit reason-use count, timestamp of last reason use in conflicts.
- On a **successful enqueue** carrying a learned-clause reason, update the
  counters. This includes the first asserting-clause enqueue. `reused`
  measures subsequent reason uses; it is not a causal benefit estimate.
- At C7's preexisting deletion-candidate scoring stage, a learned clause
  with at least 2 total reason uses and a reason use in the last 3000/6000
  conflicts gets a bounded **score discount**, making it less likely to be
  deleted. It is not an absolute exemption; other C7 limits still apply.
- When a clause is deleted, erase its C26 metadata. During safe clause
  compaction, remap the metadata through the identical clause-ID remapping
  already used for learned-clause LBD, age and live propagation reasons.
- The existing source-derived XOR/GF(2) preprocessing and full native CDCL
  are reused unmodified for `C26_REUSE6K_GF2`. This is **not** a novel
  GF2-on-CDCL-trail propagation algorithm. The standalone source-GF2
  contradiction is independently checked against original clauses before
  being counted as verified UNSAT.
- All other modes stay untouched as controls, on an isolated experimental
  branch; no changes to stable main, original SATLIB archives, original
  CNF SHA, or prior audit artifacts.

## Scoring / certification

- Original-CNF SAT models are checked against every source clause.
- Original-CNF UNSAT is counted only on independently checked GF(2)
  contradiction core. Other UNSAT outputs are explicitly `UNSAT_UNVERIFIED`;
  DRAT/LRAT verification remains a future task.
- `PAR2_verified_s` penalizes any unverified or unresolved attempt at
  2 × cap. End-to-end measured time includes spawned process + witness /
  certificate checking. Child CPU and validation time also logged.
- Each solver receives one logical CPU via taskset, with OS resource limits
  and separate process executions. No multi-core portfolio.
- The 10-SHA regression and 6-SHA extension cohorts are **nonblind**.
- The 30 generated formulas from all 15 synthetic families (indices 170 and
  171) are prospective relative to frozen historic index registries.
  We make NO claim of globally first-seen blind CNFs.
- All arms run on identical source SHA and repetitions. Sources are not
  selected by outcome. Fail closed on SHA mismatch, missing native arm
  activation, invalid SAT witness, invalid GF(2) proof or SAT/UNSAT conflict.
- 8 arms × 2 repeats × (10 + 6 + 30) = **736 matched trials**.
  Fresh cohort is distributed over 4 shards, with independent E2E caps
  10s regression / 12s extension / 8s fresh.
- No policy is adjusted based on the benchmark results.

## Artifact provenance and SQL

The audit verifies all 46 unique original source SHA, 736 trials,
oneCPU manifest flags, full arm/rep coverage and independent proof flags.
The SQLite artifact contains `source`, `trial`, `decision_event`
tables. Its `decision_event` represents `trial_completed` only;
it is **NOT** a journal of per-conflict CDCL online learning. Keep those
semantics separate from the persistent policy-learning experiments in
ATLAS15/16.

## Acceptance / follow-up

The C26 reuse hypothesis is supported only if PAR2_verified improves
without a material regression in E2E, verified SAT count, source family
coverage or peak clause memory. A large speedup on a smoke formula is
exploratory, NOT evidence of global superiority. A pure GF(2) win on a
verifiable UNSAT family is reported separately from general CDCL runtime
quality. Before selecting a winner for promotion, run a preregistered
source-disjoint prospective holdout with independent UNSAT verification
for each reference solver and track per-SHA paired effects.
