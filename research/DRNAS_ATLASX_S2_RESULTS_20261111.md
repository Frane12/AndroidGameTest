# DRNAS ATLAS-X S2 — strict lazy-expansion cost gate (2026-11-11)

## Experiment

Branch: `experiment/drnas-atlasx-structured-s2-gate-20261111`.
Run: https://github.com/Frane12/AndroidGameTest/actions/runs/42936656339
Result: **success** for correctness and all 8 source shards.

S2 differs from frozen S1 by exactly two `research/drnas_atlasx.cpp`
control-flow thresholds: after a proof-checked local rewrite saving at least
8 literals, stop further L2 search; otherwise, only attempt expensive
5-variable CNF expansion when source supports share at least **two** variables.
Direct compressed bitmask implication checks remain available for other pairs.
No changes to ATLAS1, R3C, source selection, archives, seeds or controls.

The generator and sources are identical to S1. Thus this is an **engineering
ablation** on reused frozen sources, not a new strictly blind holdout.
Original-CNF SAT witnesses independently checked for every SAT answer;
no UNSAT claims or LRAT.

## Matched 8 source x 3 repeat x 5 arms = 120 trials (one CPU, cap 8s)

| Cohort | Arm | Verified SAT | PAR2 total seconds |
|---|---|---:|---:|
| External SATLIB (2 logistics + 2 flat graph coloring) | Native A | 12/12 | 0.308313 |
| External SATLIB | ATLAS1 | 12/12 | 0.321899 |
| External SATLIB | ATLASX S2 | 12/12 | 0.312962 |
| External SATLIB | Kissat | 12/12 | 0.423979 |
| External SATLIB | CaDiCaL | 12/12 | 0.228747 |
| Planted controls (2 redundant + 2 ordinary gates) | Native A | 12/12 | 0.052477 |
| Planted controls | ATLAS1 | 12/12 | 0.052321 |
| Planted controls | ATLASX S2 | 12/12 | 0.061061 |
| Planted controls | Kissat | 12/12 | 0.057533 |
| Planted controls | CaDiCaL | 12/12 | 0.062801 |

External S2 AX / A = 1.01508 (1.51% slower), compared to S1's 1.06528.
Synthetic S2 AX / A = 1.16358 (16.36% slower), compared with S1's
1.61054. These ratios are from separate full matched runs and can reflect
runner noise: the *within-run* ratios are the proper reported metric.

### Source-level PAR2 totals (three reps)

| Shard | Source | A | ATLASX S2 | AX commits | AX L2 CNF expansions |
|---|---|---:|---:|---:|---:|
| 0 | logistics rank 2 | 0.071187 | 0.074395 | 0 | 0 |
| 1 | logistics rank 3 | 0.092086 | 0.094222 | 0 | 0 |
| 2 | flat200-479 rank 13 | 0.112531 | 0.113473 | 0 | 0 |
| 3 | flat200-479 rank 17 | 0.032509 | 0.030872 | 0 | 0 |
| 4 | planted redundant seed 0xA715 | 0.015088 | 0.014692 | 3 | 0 |
| 5 | planted redundant seed 0xB37C | 0.013756 | 0.013441 | 3 | 0 |
| 6 | planted AND/XOR/ITE seed 0xC5E2 | 0.012353 | 0.017230 | 0 | 0 |
| 7 | planted AND/XOR/ITE seed 0xD940 | 0.011280 | 0.015698 | 0 | 0 |

## Falsifiable findings

- S1: **72 L2 expansions**, only 6 ATLASX committed rewrites on synthetic
  redundant controls. S2: **0 L2 expansions**, same 6 rewrites. The expensive
  extended expansion can now remain entirely asleep on these sources.
- External original SATLIB group: 0 productive rewrites in both S1 and S2.
  Their supports did not trip the existing exact repeated-support L0 detector
  in the first 900 eligible scanned clauses. This is an incomplete detector,
  not evidence that graph coloring or planning contain no useful relations.
- ATLAS1 committed on both planted standard-gate sources, while AX S2 did not.
  Engineering priority is to recognize a local gate's complete CNF support
  across *subset supports* (e.g. AND ternary + two binary clauses), with
  a cheap index, no new unsound equisatisfiability transformations.
- The remaining S2 ~1.5% external regression is not significant evidence of
  loss or benefit given ~20ms jobs and 3 repetitions.
- This experiment is a concrete soundness/overhead advance, not a demonstrated
  improvement over Kissat or CaDiCaL in general.

## Recommended S3 (not yet implemented)

A source-only high-precision *subset-support* structural detector, careful
one-CPU E2E profiling, and a previously unused structured-source holdout.
Do not benchmark-select instances on measured results. Keep frozen S1/S2
branches unchanged, compare separately from the synthetic positive controls.
