# DRNAS MRE3 P1 — Two-formula early gate and clause-level CDCL causal ablation

2026-11-08. Research branch:
experiment/drnas-mre3-twoformula-cdcl-ablation-20261108.

Repository: Frane12/AndroidGameTest
Source run: 42486847349. Both real formula jobs succeeded, 48/48 native
measurements completed; the original audit job FAILED only because it did not
download the original frozen manifest into the audit job.
Independent artifact re-audit run: 42487380547 PASSED, using exact original
manifest and all 48 prior measurements. Original source run MUST NOT be
misreported as completely green.

Test protocol: two previously used official SAT2026 original CNFs, 2 frozen
seeds × 2 repeats, 7 arms on SAT case (28 records), 5 arms on UNSAT case
(20 records). Library: pinned CryptoMiniSat 5.11.15. OTF Gauss disabled.
Original SAT witnesses independently validated. UNSAT still has no
independent LRAT proof. This is development / NOT blind holdout.

## A: UNSAT official-12cd0c3196589ac8105653cbfe613fc6.cnf

A cheap DIMACS-header clause count check is now placed BEFORE Python
full-CNF parsing, parity block extraction, mathematical derivation and gate.
Large sources bypass costly processing and invoke original native CMS.

| Mode | sum full wall, 4 runs | preparation total | CDCL decisions |
|---|---:|---:|---:|
| Legacy MRE2 derived gate | 15.285286s | 4.806732s | 185340 |
| MRE3 early guard | **10.526755s** | **0.004184s** | 185340 |
| MRE3 guard repeat | 10.567192s | 0.004114s | 185340 |
| Native CMS | 10.530387s | 0.004147s | 185340 |
| CMS + XOR | 11.647735s | 1.558744s | 185340 |

MRE3 early guard reduces wall time by 31.13% / speeds up 1.452x relative
to Legacy MRE2 on this case. All arms show exact same real native CDCL
propagation/conflict/decision counters, so the speedup stems from removing
pre-solve overhead, not changing search.

## B: SAT official-28dcc4119e1bbb5fbd3fdd8f4140f28d.cnf

8 proof-replayed certified CRR clauses; bounded MRE2 gate selects exactly 2.
MRE3 tests each selected clause in isolation, both together, all 8, and
controls, using identical frozen seeds.

| Arm | 4-run total wall | mean native propagations | mean decisions | mean conflicts |
|---|---:|---:|---:|---:|
| native CMS | 41.484422s | 1518557 | 68997 | 56005.5 |
| XOR-only | **33.971875s** | 1791977.5 | 72344.5 | 56012 |
| CRR shadow, none imported | 34.659466s | 1791977.5 | 72344.5 | 56012 |
| CRR both gated | 34.773232s | 2436701 | 72397.5 | 56013.5 |
| CRR clause #0 only | 35.404445s | 2222406.5 | 71815.5 | 56008 |
| CRR clause #1 only | 37.270868s | 1899070.5 | 71203 | 56005 |
| CRR all 8 | 35.171587s | 1757155.5 | 72271.5 | 56019.5 |

Compared with XOR-only, clause #1 alone decreases decisions by ~1.58%,
but increases cumulative wall time by ~9.71%. Both selected clauses
together are ~2.36% slower than XOR-only, despite one seed where the
combined arm is faster. Individual clause presence clearly perturbs
native CDCL work; higher raw propagations and fewer decisions are
neither individually sufficient criteria for wall-clock acceleration.

Each isolated clause has a frozen clause SHA:
- lemma_0: 0c7500232cea21dca3695acf7ea31df299682a2b30a6daa83d35d8b788fbf397
- lemma_1: c6a319fa444515288de11253d0eb8ea98cd7efbef62b2ebe1bb99558fda791c8

### Interpretation and limits

MRE3 P1 measures real CMS native propagations, conflicts, and decisions
under exact per-lemma presence ablation. That is causal comparative
evidence about input clause influence, NOT proof of a named clause
being used as a watched propagation reason or actual conflict clause.
A future source-instrumented CMS build should tag binary watch IDs from
the imported clauses and record actual per-clause unit/conflict events
INSIDE the CDCL propagation loop.

This study uses two REUSED formulas and only two unique seeds per formula.
No broad/world-class ranking claims; no independent UNSAT LRAT.

### Immediate next hypothesis

Use a zero-to-tiny early eligibility check before MRE1 derivation;
restrict CRR to sources where evidence from native CDCL counters or a
source-instrumented watch/reason hook predicts better end-to-end wall
time, not just more propagations or fewer decisions. Compare on a small
new blind SAT2026 holdout only after proving safe native event tracing.
