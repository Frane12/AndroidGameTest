# DRNAS-SAT V7.2.1 — Independent Benchmark Results (31 Oct 2026)

Branch: `research/drnas-sat-confidence-v7-2-1` (no change to main).

## What was tested
Pinned CaDiCaL 3.0.1 C++ library, 408 new synthetic CNFs from 12 generators in two independently seeded runs, 3 repeats per method. Solver contents and SAT results were identical; all SAT models were checked. Time includes solver construction, heuristic and solve, but excludes input file reading identically across methods.

- [Holdout workflow #41195106631](https://github.com/Frane12/AndroidGameTest/actions/runs/41195106631)
- [Replication workflow #41195144948](https://github.com/Frane12/AndroidGameTest/actions/runs/41195144948)

## Results, sum of per-instance median wall time
| Mode | Time (ms) | Speedup vs plain |
|---|---:|---:|
| Plain CaDiCaL | 13280.568 | 1.000x |
| Always-majority phase | 10540.393 | 1.260x |
| Old DRNAS V7.2 | 12250.189 | 1.084x |
| DRNAS V7.2.1 confidence | 12067.139 | 1.101x |
| Confidence gate + random signs | 14537.415 | 0.914x |

For a diagnostic label of **at least 5% gain** with unconditional majority phases vs plain CaDiCaL:
| Classification metric | V7.2 | V7.2.1 |
|---|---:|---:|
| Selected | 181 | 136 |
| True positive | 99 | 93 |
| False positive | 82 | 43 |
| Precision | 54.7% | 68.4% |
| Recall | 55.9% | 52.5% |

These labels are measurement-based and noisy, especially on microsecond-scale instances. 47.6% fewer false positives with a small recall reduction is the main improvement. Time analysis is 8.12 µs on average in run 1 and 12.19 µs in run 2, including hint preparation when selected.

## Locked gate
- nvars >= 120
- 3.65 <= number of clauses / number of variables <= 4.10
- at least 90% of 64 sampled clauses are ternary
- <=3% repeated co-occurring variable pairs in 128 evenly spaced sampled clauses
- If selected, apply majority-sign phase suggestions only to variables passing the original V7.2 15% imbalance and occurrence filters. Otherwise call unchanged CaDiCaL.

This gate was selected after looking at earlier V7.2 results, NOT these two 204-case holdouts. It was not changed during the holdout and replication.

## Scientific limitations
- Synthetic tests are not representative of SAT Competition distributions.
- Always-majority had higher overall aggregate speedup, but can also have large regressions. V7.2.1 is a conservative risk/coverage trade-off.
- Performance gains are concentrated in relatively few challenging instances; per-instance accuracy is not equivalent to speed gains.
- Agreement on UNSAT outputs does not replace formal proof-certificate checking.
- Bootstrap resampling over these generated cases does not prove out-of-distribution gains.

Next: independent SAT Competition datasets, PAR-2 & solved-count analysis and stronger diagnostics of selection costs and generalization.
