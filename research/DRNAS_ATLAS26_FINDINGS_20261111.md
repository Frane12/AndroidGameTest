# ATLAS26 FINAL FINDINGS — 2026-11-11

**Run:** https://github.com/Frane12/AndroidGameTest/actions/runs/43013990071  
**Branch:** `experiment/drnas-atlas26-reuse-gf2-proof-20261111`  
**Code:** `research/drnas_atlas26_build.py`, `research/drnas_atlas26_benchmark.py`,
`research/drnas_atlas26_audit.py`, and `.github/workflows/drnas-atlas26-reuse-gf2.yml`.  
**Status:** build ✅, native selftest ✅, 16-trial smoke ✅,
6/6 matched matrix jobs ✅, audit and SQLite integrity check ✅.

## Protocol and accounting

- 46 SHA-unique CNFs: 10 SATLIB regression (nonblind), 6 SATLIB extension
  (nonblind), 30 synthetic generated sources (prospective relative to checked
  historic indices 170/171; **not** claimed globally blind).
- 8 solver arms, 2 repetitions per SHA = **736 matched trials**, one logical
  CPU per process. Caps: 10s/12s/8s. Different caps and source populations are
  kept in separate tables; do not aggregate into a universal speedup.
- SAT witness validated on original CNF. UNSAT is certified **only** with an
  independently reconstructed source-derived GF(2) contradiction. Kissat and
  CMS UNSAT outputs without independent LRAT/DRAT are **uncertified** and
  penalized in verified PAR2.
- CPU child, E2E, independent verification, reductions, BCP visits, reasons,
  LBD low-count, clause allocation and RSS are recorded. No on-holdout tuning.

## Original SATLIB regression — 10 CNFs × 2 repetitions

| Arm | SAT verified /20 | GF2 UNSAT certified | Verified PAR2, s | E2E, s | Learned clauses deleted |
|:--|--:|--:|--:|--:|--:|
| Kissat | 12 | 0 | 160.3570 | 10.8091 | n/a |
| CMS | 12 | 0 | 161.2139 | 33.4017 | n/a |
| A | 12 | 0 | 162.2134 | 41.8231 | 0 |
| **C26_REUSE3K** | **12** | 0 | **169.2786** | **44.7084** | 286,437 |
| C26_REUSE6K | 12 | 0 | 172.8321 | 46.9714 | 301,404 |
| C26_REUSE6K_GF2 | 12 | 0 | 172.8193 | 46.8739 | 301,404 |
| C7_ADAPT | 11 | 0 | 203.5381 | 68.1483 | 438,037 |
| C7_ADAPT_GAUSS | 11 | 0 | 203.6526 | 68.2533 | 438,037 |

C26_REUSE3K vs C7: **1.202× better verified PAR2**, **1.524× lower total
E2E time**, and one additional SAT witness across the 20 trials. Learned
clause deletions fell by 34.6%; watch visits fell from 799,923,774 to
483,989,360. Runtime is still **4.14× worse than Kissat by summed E2E**
and verified PAR2 is 5.6% worse than Kissat.

Example paired diagnostic (not an overall speedup claim):
`uf250-1065`, index 1, rep 0: C7 9.538313s vs C26_REUSE3K 0.916507s
(10.41×) vs Kissat 0.052100s. One source with rep 1 differs, so retain
all paired cases in any publication.

The result is **nonblind**. It is useful for design but not a valid general
SAT leadership claim.

## Original SATLIB extension — 6 CNFs × 2 repetitions

| Arm | SAT verified /12 | GF2 UNSAT certified | Verified PAR2, s | E2E, s |
|:--|--:|--:|--:|--:|
| Kissat | 8 | 0 | 97.1821 | 10.4405 |
| CMS | 8 | 0 | 104.2815 | 37.8074 |
| C7_ADAPT | 7 | 0 | **134.5618** | **58.7307** |
| C26_REUSE6K | 7 | 0 | 136.3801 | 60.7316 |
| C26_REUSE6K_GF2 | 7 | 0 | 136.3176 | 60.7434 |
| C7_ADAPT_GAUSS | 7 | 0 | 136.2975 | 60.4688 |
| C26_REUSE3K | 6 | 0 | 152.0471 | 64.3737 |
| A | 6 | 0 | 146.2040 | 59.2055 |

**Important regression:** REUSE3K is 13.0% worse on verified PAR2,
9.6% worse on E2E and loses one verified SAT relative to C7. The 6K
variant preserves C7's verified SAT count but does not beat its PAR2.

## Synthetic prospective, 15 categories × 2 instances = 30 CNFs

| Arm | SAT verified /60 | GF2 UNSAT certified | Verified PAR2, s | E2E, s |
|:--|--:|--:|--:|--:|
| C7_ADAPT | 44 | 0 | 256.2092 | 0.5756 |
| C26_REUSE3K | 44 | 0 | 256.2079 | 0.5556 |
| C26_REUSE6K | 44 | 0 | 256.2108 | 0.5595 |
| C7_ADAPT_GAUSS | 44 | 4 | 192.2282 | 0.5720 |
| C26_REUSE6K_GF2 | 44 | 4 | 192.2272 | 0.5614 |
| Kissat | 44 | 0 | 256.3375 | 0.4643 |
| CMS | 44 | 0 | 256.2456 | 0.4129 |

The four GF(2) independently verified attempts are **two unique formula
SHA** (`xor_chain_unsat`, indices 170 and 171, two repetitions each).
Both C7+GF2 and C26+GF2 give the same 3-row source XOR certificate, so
the 1.333× verified-PAR2 advantage over no-GF2 is **not a new C26 search
improvement**; it is existing mathematically provable UNSAT machinery.

All arms' E2E times on this synthetic batch are below one second total:
small variations here are not robust statistical evidence.

One informative shard recorded 45,444 learned-clause reason uses,
37,794 reuses, 3,354 down-ranked deletion candidates, 6,190 safely
migrated metadata entries after compaction and 1,578 deletes (vs 1,595
for C7). This demonstrates instrumentation and a causal change in
clause-selection policy; not a universal speedup.

## Memory and BCP observations

- Regression peak clause allocation: C7 3,297,232 B; C26_REUSE3K
  3,276,900 B; C26_REUSE6K 2,542,044 B. Peak RSS reported
  26,068 KiB for all native arms. The clause-allocation metric excludes
  the overhead of C26's `std::map` metadata.
- Extension peak clause allocation: C7 2,401,776 B; C26_REUSE3K
  2,029,452 B; C26_REUSE6K 2,251,088 B. Peak RSS 33,244 KiB
  for all native arms.
- `watch_visits` is a BCP work proxy, **not measured wall time**.
  More or fewer visits do not imply proportionate CPU improvement.
- LBD is tracked in the native solver. The new telemetry counts low-LBD
  clauses at creation and actual propagating reason uses, but does not
  yet establish proof of utility of every retained clause.

## Reproducibility, SQL, and limitations

- Final independent audit checked source SHA disjointness and 736 unique
  trial keys (SHA, repetition, arm), verified SAT witnesses and GF2 core
  flags, per-cohort caps, one logical CPU, and manifest hashes.
- SQLite `atlas26_events.sqlite`: 46 source entries, 736 trial entries,
  736 `trial_completed` events, integrity check `ok`, 823,296 bytes.
  **These are trial events, not live per-CDCL-decision online learning.**
- Artifacts: workflow run's `ATLAS26-FINAL-AUDIT-SQL`, 6 matched JSON/log
  artifacts, smoke and binary artifact. No edits to stable branch, inputs,
  frozen baseline source or previously completed results.

## Decision

**Do not promote C26_REUSE3K or C26_REUSE6K to default.** C26_REUSE3K
produces a material speedup on one historical cohort but regresses on
another historical cohort, while on new generated easy formulas it shows
no meaningful PAR2 improvement over C7. The hypotheses remain plausible
and should be tested with a truly unseen, harder source-disjoint SATLIB
cohort, with matched 1CPU trials, correct reference UNSAT proofs, LBD/
reuse statistics and memory-aware BCP budget.

Next proposed isolated experiment: pre-register a bounded rule that
activates reason-use scoring only when actual live CDCL telemetry indicates
stagnation and high watch pressure; compare separately against C7,
C26_REUSE3K, C26_REUSE6K, and controls. The current benchmark **must
not** be used to tune thresholds on the same SHA.
