# DRNAS ATLAS18 — causal learned-clause retention factorial (2026-11-11)

Branch: `experiment/drnas-atlas18-retention-factorial-20261111` (strictly experimental).
Frozen parent: `experiment/drnas-atlas17-bcp-adaptive-20261111`.
**This experiment is separate from the other ATLAS18 GF2-selective line of work**.

## Prior findings, limitations
ATLAS17, run 42971761657, completed 3200 oneCPU E2E attempts across 200
source SHA and demonstrated C7 reported PAR2 481.99 s vs C6 568.97 s
(1.1805x). Verified PAR2 C7 2053.44 s vs C6 2131.72 s;
C7+Gauss 1733.75 s with 20 original-CNF independently verified
GF2 UNSAT attempts. C7 deleted ~616k clauses vs ~9.5k C6.
This shows an improvement in aggregate, but **not** that the high deletion
quota, the increased deletion frequency, or the adaptive pressure gate
individually caused the improvement. This experiment isolates those factors.

## Pre-registered prospective factorial: 2 x 2
The two orthogonal factors are:

| Factor | Level 1 | Level 2 |
|---|---|---|
| Scheduling | FAST: every 1500 conflicts | GATE: 1500 at watch/prop >8, otherwise every 3000 |
| Deletion quota, of eligible weak unlocked clauses | 1/8 | 1/16 |

Arms:
- `C8_FAST_Q8`: every 1500, eligible 1/8
- `C8_FAST_Q16`: every 1500, eligible 1/16
- `C8_GATE_Q8`: pressure gated, eligible 1/8
- `C8_GATE_Q16`: pressure gated, eligible 1/16
- Frozen reference `C6_KEEP`, frozen `C7_ADAPT`, certified GF2 reference
  `C7_ADAPT_GAUSS`, independent `KISSAT` and `CMS`, plus DRNAS `A`.

C6/C7 modes remain behaviorally identical to parent; C8 is new and isolated.
No novel propagations, SAT rules, UNSAT rules, or original-formula edits.
Reasons/binary and good glue clauses remain locked/protected. C8 enables only
the clause deletion cadence and quota logic; original CNF is SHA verified.

## Frozen holdout and reproducibility
- 20 families x5 sources, indices 95..99 of original pinned SATLIB sources
  and deterministic generators: 25 original SATLIB and 75 synthetic.
  ATLAS16 used indexes 35..84, ATLAS17 85..94; 100 new SHA in this run.
- 10 arms x2 repetitions x100 source SHA = **2000 matched attempts**.
- One logical CPU, 8s E2E limit, pre-registered SHA and frozen ATLAS15 policy;
  no use of this holdout for branch learning.
- Each smoke-tested build is compiled once; 10 shards of 10 sources each.
- Per attempt: original model verification; original-SHA witness; certified
  GF2 UNSAT by reconstructing the source XOR contradiction; non-certified
  UNSAT is never counted as solved for *strictly verified* PAR2.
- Append every trial, telemetry (watch visits, propagations, pressure cycles,
  deletions, reclaimed slots, E2E, PAR2), source SHA and outcome in SQLite.
- The third-party Kissat and CryptoMiniSat references are single-threaded,
  with source-original SAT verification but **no LRAT proof credit for UNSAT**.

## Criteria / caveats
Primary: pair-matched reported and verified PAR2 and SAT verified solved counts.
Secondary: total watch visits, watch/prop ratio, deletion volume, compactions,
peak RSS (not inferred from slots reclaimed), and per-family outliers.
Look at factorial contrasts:
- At fixed Q8: C8_FAST_Q8 vs C8_GATE_Q8 (scheduling)
- At fixed Q16: C8_FAST_Q16 vs C8_GATE_Q16 (scheduling)
- With FAST: C8_FAST_Q8 vs C8_FAST_Q16 (quota)
- With GATE: C8_GATE_Q8 vs C8_GATE_Q16 (quota)
Keep the conservative candidate only if there is no correctness disagreement,
if PAR2 and verification coverage do not regress, and resource use is acceptable.
The 100-source cohort is an exploratory discovery sample, *not* sufficient alone
for general claims. Confirm winning parameter choice on an additional
independent original-CNF holdout before promoting to stable.
