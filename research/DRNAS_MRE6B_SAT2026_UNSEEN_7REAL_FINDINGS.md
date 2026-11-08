# DRNAS MRE6b — official SAT2026 documented-source-disjoint blind holdout

Date: 2026-11-08.
Branch: experiment/drnas-mre6b-official-unseen-holdout-20261108
Initial frozen source set: GitHub run 42495094599.
Successful paired replay of the EXACT pre-solve-frozen source data:
https://github.com/Frane12/AndroidGameTest/actions/runs/42495311707
Status: ALL four paired shards succeeded, final independent audit PASSED.
Native library is identical SHA-pinned MRE5 instrumented CryptoMiniSat 5.11.15,
and all arms disabled OTF Gaussian elimination.

## Prospective selection before performance

Seven official SAT Competition Main 2026 original CNFs:
4 official verified SAT and 3 official verified UNSAT. The first frozen
source run excluded 294 prior official GBD identifiers from declared
historical registry logs, R32p and conservative R82 eligibility ranges.
Selected from 400 official sources by precommitted salted GBD ordering,
published official SAT/UNSAT status balance and predeclared <=12MiB,
<=12k variables, <=35k clauses limits. Never select by equality/XOR
structure or measured solving time.

**Scope caution:** historical registry intentionally lacks guarantees of
complete coverage of every unrecorded past benchmark. These are verified
source-disjoint from the declared historical registry and the previously
used MRE6/MRE6b training source, NOT proven globally never touched.

The first run 42495094599 had a packaging failure AFTER successful source
freeze; no source was solved in it. Its exact frozen original CNFs and
pinned CMS were downloaded unchanged in successful run 42495311707.
No resampling, substitutions or cherry-picked exclusions were allowed.

## Frozen real formula list

| Official GBD ID | Published status | Clauses | Certified equality? |
|---|---|---:|---|
| 6ad453d6174581d982c4e75e37a38d79 | UNSAT | 3309 | no |
| db099269d468029b70419bf4a49e99a1 | SAT | 30926 | no |
| 15456f0d13b26f0b4b21525ef7d0d711 | UNSAT | 20035 | no |
| a45aefde8bb26edb9634004146d0de89 | SAT | 22688 | YES, two original complementary implications |
| 782b29d2d691fdc94e0ec5b899390e10 | SAT | 17700 | no |
| de8c42d50f1dbf43a731f1916dc6bf01 | UNSAT | 9573 | no |
| 2fcd8533eba981967292f1b6e41f7433 | SAT | 11072 | YES, two original complementary implications |

## All 56 trials: 7 formulas × 2 SHA-paired repetitions × 4 modes

4 modes (identical native CMS source and seed):
- original CNF no XOR imports
- original CNF with certified source XOR imports
- proof-certified variable equality quotient, no source XOR imports
- same quotient with certified/transported source XOR imports

Per arm: 14/14 attempts TIMEOUT at **18s full wall**, 0/14 solved.
All 4 arms have identical PAR2 = 504s. This is NOT a tie in underlying
solve efficiency; all runs were censored at 18s and native cumulative
CDCL counters / CPU solve counters were not collected at timeout.

The native bridge's CPU timer only emits a result if cms.solve() returns;
on subprocess cutoff no partial solve CPU/propagation counters are available.
Do NOT claim this audit demonstrates MRE6b speeding up or slowing down
the actual solving trajectory on these 7 real sources.

The equality-rewrite applicability rate is 2/7; on 5/7 cases the proof
finder correctly abstains (no unproven elimination). Preprocessing costs
are included in end-to-end cap, including 18s limit.

Across 14 attempts per mode (seconds of total measured preprocessing wall):
- original CNF without XOR: 0.626016s
- original with certified source XOR: 2.023374s
- proof-search+quotient with imported XOR: 9.012464s
- proof-search+quotient without XOR: 9.109764s.

This is a real presolve cost (~0.64s on average for quotient attempt vs
~0.045s average for original no-XOR input); it is a strong reason for a
cheaper candidate eligibility guard on no-equivalence formulas.

Correctness: original source SHA verified in each trial, source pairing
and pinned native checks passed, no SAT solver verdicts before cutoff.
Official published statuses were recorded, but no UNSAT result is
independently proven with LRAT in this run.

## Scientific conclusion

This genuine new-source holdout offers *no speedup evidence* at 18s.
It does establish that actual proof-certified positive equivalences
occurred in 2 new official SAT2026 formulas. The method is **not**
universally applicable, and source-blind eligibility and fallback
overhead deserve as much scrutiny as successful quotient transformations.

Future prioritized tests:
1. On exactly the two newly eligible official sources, use a longer
   diagnostic horizon or an interruption-aware CMS bridge that emits
   native CPU/BCP counters at the cap. Label any targeted follow-up as
   diagnostic (not a fresh blind source holdout).
2. Use a fresh source-disjoint official fast/medium stratum, precommitted
   using external official reference rather than DRNAS timings, to
   obtain solved-versus-solved end-to-end comparisons.
3. Require total preprocessing+proof+model-reconstruction costs and
   independent UNSAT proof validation before general solver claims.
4. Keep all MRE6b CPU-aware mathematical hypotheses in experimental
   shadow mode; do not promote a target-dependent policy based on this
   censored holdout.
