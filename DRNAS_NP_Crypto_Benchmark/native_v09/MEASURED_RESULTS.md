# DRNAS NP v0.9 — measured native CaDiCaL decision-phase results

**Completed GitHub Actions:** https://github.com/Frane12/AndroidGameTest/actions/runs/41199540301

**Source and raw timing artifact:** https://github.com/Frane12/AndroidGameTest/actions/runs/41199540301/artifacts/13041514768

## What this experiment did

Native C++ `CaDiCaL::Solver::phase(lit)` decision-polarity hints,
without assumptions or clause changes. Baseline and five adaptive
variants share the exact **same libcadical backend and original CNFs**.
Each of 60 previously used third-party CNFs and 36 new constructed
controls were run three times with counterbalanced order.

**Correctness:** 1,680 brute-force-verified combinations in seven native
modes, additional contradiction tests, all SAT witnesses checked against
original CNFs. CryptoMiniSat independently checked external SAT/UNSAT
labels where it finished. No wrong SAT/UNSAT outcomes recorded.

## Primary external regression findings

For the 60 external formulas (57 with CryptoMiniSat reference results),
the plain CaDiCaL baseline solved 168/171 reference-known repeats.
Unsolved attempts are NOT turned into speed wins.

| Variant | Matched complete pairs | Win pairs | Mean paired gain, ms | Median paired gain, ms |
|---|---:|---:|---:|---:|
| Horn-only v0.8 | 168 | 78 | +0.024 | -0.0017 |
| All majority phases | 168 | 63 | +38.667 | -0.0074 |
| All minority phases | 154 | 74 | +1.977 (selection-biased) | -0.0015 |
| Selective majority phases | 165 | 64 | -2.784 | -0.0065 |
| Horn + selective phases | 165 | 74 | -3.077 | -0.0043 |

The mean improvement for majority is strongly dominated by a few
**previously tested third-party synthetic Byt-Wyze formulas**. No broad
improvement is established; most individually completed pairs are
marginally slower, while some expensive examples improve dramatically.

Stable three-repetition medians on notable hard CNFs (all reference
SAT/UNSAT independently confirmed):

| File | Truth | Baseline ms | All-majority ms | Approx. ratio |
|---|---|---:|---:|---:|
| sat-Moderate-B-26810conflicts-longclauses.cnf | SAT | 1048.45 | 50.60 | 20.72x |
| sat-Easy-B-2181conflicts-longclauses.cnf | SAT | 449.03 | 30.49 | 14.73x |
| unsat-Hard-C-126197conflicts-transition.cnf | UNSAT | 1814.00 | 1117.56 | 1.62x |
| unsat-Moderate-C-37673conflicts-saturated.cnf | UNSAT | 723.37 | 532.05 | 1.36x |

**Counterexamples also matter:** `unsat-Moderate-B-26048conflicts-transition.cnf`
became slower (~248.53 -> 324.06ms) with all-majority. A different
variant (minority) failed to finish some SAT cases that baseline solved,
and the selective gate also caused timeouts for the moderate-B SAT
instance. This shows that phase hints alter search trajectories,
not correctness, and can be highly beneficial or harmful.

On 12 manufactured renamable-Horn SAT controls, keeping the original
exact Horn shortcut remains the reliable gain: 0.260 -> 0.202ms
median and 34 of 36 run pairs faster. All-majority hints alone do not
beat this dedicated solver.

## Next mandatory scientific check

A predefined independent **20-formula Byt-Wyze holdout** with 10
SAT-labelled and 10 UNSAT-labelled files, chosen reproducibly by
predeclared random seed **without reusing any of the original 16**
and without tuning thresholds on the results:
https://github.com/Frane12/AndroidGameTest/actions/workflows/drnas-np-v091-phase-holdout.yml

Even if that heldout succeeds, this is not a P vs NP result or evidence
of a universal SAT advantage. A robust domain-specific selector would
still need statistical validation on diverse real application datasets
and must account for cases that fail to finish.
