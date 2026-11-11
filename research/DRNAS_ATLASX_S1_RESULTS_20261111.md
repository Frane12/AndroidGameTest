# ATLAS-X S1 — structured source holdout audit

Run: https://github.com/Frane12/AndroidGameTest/actions/runs/42936015934

## Protocol actually run

Four SATLIB original source SHA-pinned formulas (planning logistics ranks
2/3, graph-coloring flat200-479 ranks 13/17); four deterministic planted
Boolean-control formulas (redundant rels seeds 0xA715/0xB37C, standard
AND/XOR/ITE gate circuits seeds 0xC5E2/0xD940). Total 8 distinct sources x
5 solver arms x 3 reps = 120 matched one-logical-CPU trials, 8s cap, PAR2
16s for UNKNOWN, original model verification on every SAT answer.
No independent UNSAT LRAT is claimed. Synthetic source status is independently
checked against the planted witness; external SATLIB archive SHA verified.

## Results — *do not pool synthetic with real-world when claiming improvement*

| Cohort | Arm | Verified SAT | PAR2 total s |
|---|---|---:|---:|
| External SATLIB | A (native clean) | 12/12 | 0.280102 |
| External SATLIB | ATLAS1 | 12/12 | 0.295791 |
| External SATLIB | ATLASX | 12/12 | 0.298387 |
| External SATLIB | Kissat | 12/12 | 0.396307 |
| External SATLIB | CaDiCaL | 12/12 | 0.211245 |
| Planted synthetic | A (native clean) | 12/12 | 0.054047 |
| Planted synthetic | ATLAS1 | 12/12 | 0.056492 |
| Planted synthetic | ATLASX | 12/12 | 0.087045 |
| Planted synthetic | Kissat | 12/12 | 0.061769 |
| Planted synthetic | CaDiCaL | 12/12 | 0.061790 |

External ATLASX / A = 1.06528 (6.53% slower) on this tiny trial set.
Planted ATLASX / A = 1.61054 (61.05% slower). Aggregate, for diagnostics
only, A PAR2=0.334149, ATLASX=0.385432 across 24 trials each.

### Per-source PAR2 total (three repetitions)

| SHA prefix / family | A | ATLAS1 | ATLASX | Kissat | CaDiCaL | AX commits |
|---|---:|---:|---:|---:|---:|---:|
| 15606aa9 planning logistics | .078437 | .085602 | .091414 | .147723 | .043935 | 0 |
| 2c8a4b65 planning logistics | .076160 | .078640 | .078693 | .117910 | .050467 | 0 |
| 93fa059e flat200-479 | .095957 | .099936 | .099220 | .056461 | .022496 | 0 |
| 70957366 flat200-479 | .029548 | .031613 | .029060 | .074213 | .094347 | 0 |
| f3419665 redundant planted | .013564 | .014187 | .019682 | .014377 | .015792 | 3 |
| 0699f955 redundant planted | .013521 | .014387 | .020239 | .019042 | .016363 | 3 |
| 8547cd72 standard gates planted | .013515 | .013911 | .023537 | .014050 | .014750 | 0 |
| a83d940a standard gates planted | .013447 | .014007 | .023587 | .014300 | .014885 | 0 |

## Structural findings

- All 12 ATLASX external SATLIB attempts stopped at
  `L0_no_composite_support`, with **zero commits/expansions**.
- Both planted redundant cohorts found **three accepted transformations each**
  (6 total across 6 repeats), demonstrating exact semantic reductions, but
  also wasted **36** extended-materialization attempts.
- Both planted ordinary-gate cohorts made zero ATLASX commits yet wasted
  another **36** expensive expansions.
- ATLAS1 found transformations on all four planted cases (12 commits across
  three repeats). The current ATLASX L1 grouping is therefore weaker for
  ordinary gates because it inspects only clauses with identical variable
  support, whereas ATLAS1 also merges support subsets.
- One CPU, SAT witness checked on original source, all solved; performance
  ranking for such short millisecond runs is vulnerable to noisy startup and
  scheduler variation. Observed regressions are diagnostic, not universal.

## Next S2 hypothesis

Keep frozen S1 unchanged. On a separate branch implement a high-precision
lazy gate that avoids expensive L2 clause reconstruction where there is no
cheap structural evidence, and prioritize inexpensive L1 subset-support
modules that can recognize standard AND/OR/ITE gate CNF.
Repeat the *same* frozen source selection for a paired engineering ablation,
then require a separate new-source holdout before broad claims.
