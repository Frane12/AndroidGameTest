# DRNAS MRE2-CDCL P1 — targeted two-formula native CDCL audit

Date: 2026-11-08. Branch: experiment/drnas-mre2-cdcl-twoformula-pilot-20261108.

Source benchmark: GitHub Actions run 42485082475, two successful per-formula
jobs and 40 original measurements; its original audit job FAILED because the
workflow did not download the frozen manifest into that job. No measurement
failed. Independent final audit-only GitHub Actions run 42485611055 PASSED
using the source input artifact and both completed 20-trial artifacts. Do NOT
present the original workflow run itself as success.

Design: two reused official SAT2026 formulas, two pinned seed values per formula,
two timing repeats per seed, five matched arms. 40 native-CMS trials total.
OTF Gauss OFF in all modes, original clauses retained, CRR lemmas verified
through MRE1 proof replay. Native SAT witnesses independently checked against
original SHA-locked CNF. Independent LRAT verification for UNSAT NOT supplied.

Telemetry: actual CryptoMiniSat 5.11.15 post-solve cumulative CDCL
get_last_propagations/get_last_conflicts/get_last_decisions. These are real
native runtime counters, NOT counters of activations attributable to each
specific imported lemma, and NOT a custom mid-CDCL DRNAS trail callback.

## Case A — official-28dcc4119e1bbb5fbd3fdd8f4140f28d.cnf, SAT

Eight certified CRR lemmas; MRE2 gate chooses two. 150 independently
certified source XOR rows per attempt.

| Arm | 4-attempt sum wall s | Mean CDCL propagations | Mean decisions | Mean conflicts |
|---|---:|---:|---:|---:|
| native CMS | 40.874565 | 1518557 | 68997 | 56005.5 |
| XOR baseline | 33.475103 | 1791977.5 | 72344.5 | 56012 |
| CRR shadow | 33.978795 | 1791977.5 | 72344.5 | 56012 |
| CRR all 8 | 34.310435 | 1757155.5 | 72271.5 | 56019.5 |
| MRE2 gate 2 | 34.113290 | 2436701 | 72397.5 | 56013.5 |

MRE2 gate causes +35.98% total native propagations versus XOR baseline yet
+1.91% cumulative wall time. By seed: gate faster than XOR by 0.29s and
0.37s (seed 1804723611), then slower by 0.62s and 0.67s
(seed 3911827663). Per-seed native counter changes deterministic across
repeated trials, while wall time varies. Propagation volume alone fails to
predict net speed; decisions/conflicts must be measured and clause-specific
activation deserves a proper CMS trail instrument in a future experiment.

## Case B — official-12cd0c3196589ac8105653cbfe613fc6.cnf, UNSAT

One certified CRR lemma, MRE2 gate selects none because the source exceeds
its bounded-probe clause limit. One certified XOR row per attempt.

| Arm | 4-attempt sum wall s | Mean CDCL propagations | Mean decisions | Mean conflicts |
|---|---:|---:|---:|---:|
| native CMS | 10.064495 | 1943219 | 185340 | 57236.5 |
| XOR baseline | 11.194280 | 1943219 | 185340 | 57236.5 |
| CRR shadow | 13.776735 | 1943219 | 185340 | 57236.5 |
| CRR all 1 | 13.976574 | 1943219 | 185340 | 57236.5 |
| MRE2 gate 0 | 13.842631 | 1943219 | 185340 | 57236.5 |

Across every seed and mode, exact same native propagation, decision, conflict
counts. MRE2 gate is 23.66% slower than XOR-only due largely to preprocessing.
The expensive MRE1 derivation happens BEFORE the size-based gate abstains.
Next cheap fix: move bounded-gate eligibility test to the front of preprocessing
and dispatch to native CMS/XOR-only immediately on oversized sources.

## Next research test — do not launch 320 jobs

Implement a cheap early abstention before certified MRE1 derivation on
oversized sources; also instrument clause-level activation (e.g., native
in-CDCL CRR learnt/watch propagation reason count) using pinned CMS source
or a supported hook if available. Compare only these same two formulas with
frozen paired seeds. Do not assume a higher propagation count indicates
improved SAT performance.

Do not generalize from two reused development formulas to blind holdout.
