# DRNAS CDCL Core Rebuild — engineering plan (experimental only)

## Decision

Do **not** mistake cosmetic changes for a redesigned SAT solver. X5.8
removed 1,436,263,721 redundant watch stores on 36 historical SAT2024
instances ×2 and improved PAR2 only 0.0022% against the same binary.
Therefore profile memory movement, pointer chasing, propagation throughput
and search quality separately.

Source baseline: `src/drnas_x5.cpp`. Frozen reference SHA remains immutable.
Experiment source: `src/drnas_x59.cpp` (X5.9).
Do not modify `main`, any frozen baseline or previous result directory.

## Existing core decomposition (verified by source inspection)

| Subsystem | Actual implementation | Concern and next step |
|---|---|---|
| CNF and clauses | `Clause { std::vector<int> lits; ... }`, `std::vector<Clause>` | Separate allocations and cache-unfriendly clause dereferences; develop contiguous clause arena retaining stable clause handles |
| BCP | `watches_[2*n]` containing `Watch{clause,blocker}`; `binary_implications_`; `propagate()` | Distinguish blocked, scanned, shifted, unit and conflict watches; capture cache and scan costs. X56 original-binary CSR did not yield a certified gain; don't retry it blindly |
| Analysis | 1-UIP `analyze()`, `minimizeClause()`, `computeGlue()` | Remove allocation/sort from glue. Track reason DAG visits and time per conflict. Never change proof validity |
| Branch selection | Lazy `priority_queue<Entry>`, generation IDs, periodic rebuild | Compare indexed heap with the exact same score and tie-break semantics |
| Restarts | Static growth + optional LBD-triggered restart | Only optimize after measuring the deterministic baseline; prior CHB/LRB trials lacked benefit |
| Learned clause deletion | `reduceLearnts()` with LBD/usage guards, `collectGarbage()` remapping reasons and watches | Protect locked reasons and short/glue clauses; measure useful-clause survival and cost |
| Proof output | Per-clause proof writes, independently checked UNSAT | Exact SAT witness and DRAT correctness are release blockers |

## Isolation rules

Only one component may differ per benchmark arm. Always compile a single
candidate executable and compare **feature OFF vs ON** to prevent compiler or
binary drift from masquerading as an algorithm gain. Also retain fixed X5,
Kissat and CaDiCaL comparison arms. Reintroduce CMS only after dynamic
linker dependencies are validated by `ldd` on every runner.

One logical CPU per solver; serial within runner; SHA-frozen original CNFs;
same cap, repeats and input ordering; shuffled arm order; complete trial
coverage and no duplicated trials; no use of previously opened holdouts as
fresh blind evidence.

## Work packages

### X5.9 — stamped decision-level glue (currently under test)

Add `--x59-stamp-glue`. Count distinct LBD levels with epoch stamps rather
than building, sorting and uniquing a vector on each conflict. Semantic
equivalence is mathematical: both count distinct integers in a given literal
sequence. Validate independently verified SAT and UNSAT models/proofs.
Primary comparisons: X59_OFF, X59_ON (same binary), frozen X5.

### X6.0 — indexed VSIDS heap

Replace duplicate-entry `std::priority_queue` with an indexed binary heap
that supports updates in O(log n), eliminates stale elements and keeps the
existing exact ordering, including variable tie-breaks. Add invariant and
differential tests: assignments, backtracks, activity bump, rescale,
`topCandidates`, random seeds and restarts. Instrument heap size, stale
pop count, heap operations, rebuilds and branch-selection CPU. Freeze the
original source unchanged in a comparison arm.

### X6.1 — compact long-clause arena

Implement a contiguous literal arena, stable 32-bit clause references,
separate metadata (LBD/activity/deletion) and garbage-collection remapping.
Keep binary implication graph independent. No speculative switching:
audit every watcher, reason, proof deletion and added clause. Measure
pointer-chasing and cache misses, memory, BCP inspected watches and
propagations per CPU-second. Start with OFF/ON same binary on retrospective
families; never merge before proof and end-to-end verification.

### X6.2 — adaptive learned-clause retention and restart

Only after the previous execution-engine changes are stable, test
LBD tiers, recency, reason usage, clause minimization budgets and restart
windows. Change one policy dimension at a time. Preserve best fixed
reference and only train on training splits.

## Benchmarks and gates

- Preflight: random planted SAT, contradiction UNSAT, PHP, XOR and
  boundary/empty/tautology cases. Every credited SAT must satisfy the
  original full CNF. Every credited UNSAT must pass an independent proof
  checker. Zero false answers, no process crash.
- Retrospective A/B: REAL36 (36 originals ×2 repeats), optional extensions
  on previously used 100+ originals with a 5, 15 or 30 second cap. Report
  each cap separately; source- and family-clustered paired CI95; collect
  conflict counts, propagation counts, CPU and maxRSS.
- Candidate screening: >5% verified PAR2 improvement over same-binary OFF,
  CI95 lower bound >0, no solved-regression, no errors. This is **not**
  evidence for a blind promotion.
- Fresh blind: new never-executed family-disjoint originals, predetermined
  30s cap, >=10% verified PAR2 improvement over preselected strongest fixed
  DRNAS control, family-bootstrapped CI95 lower >0, no reduction in solved
  SAT or UNSAT. Independent replication before any production merge.
- Existing REAL-SPEED 6h loop is development-only. Leave its separate
  preserved blind partition sealed until authorization.

## Interpretation

A 0.1% speed difference in a benchmark dominated by hard timeouts, small
source families, or compiler/runtime noise is not a meaningful core redesign.
A gain based only on unverifiable UNSAT is invalid. Report failures in the
engineering path as failures, not as solver regressions or successes.
