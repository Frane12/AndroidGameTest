# DRNAS SAT v9.6 — new official 2026 benchmark and potential individual-best candidates
31 October 2026

## Provenance
- New project-level blind 12-CNF GitHub Actions test: https://github.com/Frane12/AndroidGameTest/actions/runs/41237911915
- Verified complete data artifact: https://github.com/Frane12/AndroidGameTest/actions/runs/41237911915/artifacts/13056770952
- Published 2026 best-per-instance cross-hardware context on original 12 v9.5 instances: https://github.com/Frane12/AndroidGameTest/actions/runs/41238008121
- Official 2026 results source: https://satcompetition.github.io/2026/results.html ; official scores pinned repo commit 3e2dee7cf5aa643c77bf946280a3c1c520756ef9 and Git blob SHA 9c926b2bd35ac0fb4f3d0cf8f58c97178d43faef.
- Original 18 + later 12 official CNFs (30 total) explicitly excluded from new v9.6 cohort. 12 new official 2026 CNFs, 6 SAT and 6 UNSAT, 5 methods x 2 repeats = 120 solver processes.
- Pinned CaDiCaL 3.0.1. All five methods on identical GitHub-hosted single-core Ubuntu CPUs, 15-second per-attempt wall cap, 30-second PAR2 timeouts. No adaptation of 64/96/128/256 cutoffs after observing outcomes.

## v9.6 NEW-cohort full mean PAR2 (smaller is better)
| Mode | Solved/24 | Mean PAR2 s | Percent lower mean PAR2 vs plain |
|---|---:|---:|---:|
| CaDiCaL plain | 2 | 28.6223 | baseline |
| Single-64 | 4 | 26.3917 | 7.79% |
| Single-96 | 4 | 26.2076 | 8.44% |
| Single-128 | 4 | 25.8546 | 9.67% |
| Single-256 | 2 | 28.4671 | 0.54% |

The improvement was exclusively on SAT: all 6 UNSAT input formulas timed out on every method, so no UNSAT benefit is established. Small cohort and many censored runs. Three 64/96/128 schedules outperform plain overall; 128 is smallest mean PAR2 on this cohort, but selecting it post-hoc cannot be treated as prospective superiority.

## FIVE numeric candidates against the fastest official 2026 published result for exactly the same CNF
**Crucial: different hardware and time limits — NONE is a verified world record.**
| Case SHA prefix | Dataset timing | Our best seconds | Published fastest 2026 seconds | Published fastest solver | Numeric ratio published/ours |
|---|---|---:|---:|---|---:|
| ee44c3f46423 | Earlier viewed 12 (Single-96) | 0.4785 | 1.4700 | zhenwei_mergesat-l[main-ai] | 3.07x |
| 2b35377a7b95 | Earlier viewed 12 (Single-96) | 5.6079 | 14.6400 | biere_cadical3[main] | 2.61x |
| 8d0d8518a438 | NEW 12 (Single-128) | 4.4410 | 8.5100 | ding_kissat-mab-eae2[main-ai] | 1.92x |
| 2b8cac8e1f5c | NEW 12 (Single-128) | 5.8144 | 6.4500 | zhenwei_mergesat[main] | 1.11x |
| 3ed56242f55e | NEW 12 (Single-96) | 7.0550 | 15.9100 | liang_kissat-lr-ds[main] | 2.26x |

On new 8d0d8518, local plain CaDiCaL median 13.468 s vs Single-128 4.441 s, a 3.03x same-hardware advantage. On new 2b8cac8e, local plain CaDiCaL timed out both times, Single-128 finished both at ~5.8s. On new 3ed56242, local plain CaDiCaL timed out twice and Single-96 finished both at ~7.1s. These data are repeatable within 2 deterministic executions but not proof of broad superiority.

## Why NOT a world record
SAT Competition 2026 Main track ranks solvers by aggregate PAR2 over ~400 public competitive formulas with its own hardware, correctness checking and much longer run limits, not by a world-record registry of fastest individual CNF runs. A GitHub-run local time lower than published competition time does not establish a certified world-fastest run.
Main track published table lists kissat-sc2024 306/400 solved and CaDiCaL 284/400. Our 12-case low-budget subset is not a full-competition score.
To seriously validate an *instance-level best-known timing*: run Single-96/128 and the corresponding official top competitor's IDENTICAL submitted binary on identical physical CPUs with pinned versions, affinity and disabled noise, >=10-30 repeats, fixed memory/time limits, SAT model checking, UNSAT LRAT/DRAT proof checking, and ideally external replication by solver maintainers.
Even a best-known per-instance time would not imply P=NP, break an NP complexity class, or become an officially recognized 'SAT world record'.

## Research decision
Preserve both Single-96 (formerly best on old 12) and Single-128 (best aggregate on new 12) as candidates. Do not optimize the 128 budget on these same 12 and call the next test blind. More meaningful work: examine how a 96/128 conflict stop-and-resume affects CaDiCaL internal restart/rephase schedules and learned clause activity; add independent external real-world families, SAT/UNSAT proof validation and equal-hardware best competitive solver benchmarks.
