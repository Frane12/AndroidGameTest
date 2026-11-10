# DRNAS Native R1 vs Kissat 4.0.4 vs CryptoMiniSat 5.17 — matched original DEV4
Date: 2026-11-10
GitHub Actions **SUCCESS**: https://github.com/Frane12/AndroidGameTest/actions/runs/42859434986
Experimental branch: `experiment/drnas-native-dev4-triple-compare-20261110`
Frozen source list: `experiments/drnas_native_solveset1/FROZEN_DEV4.json`
Executable harness: `research/drnas_native_dev4_triple_compare.py`
Workflow: `.github/workflows/drnas-native-dev4-triple-compare.yml`
Artifact: `DRNAS-NATIVE-DEV4-TRIPLE-36-SAME-CPU-ONE-RUNNER-PAR2` containing full `final-report.json` and 36 individual JSON trials.

## Provenance and fairness

All 4 original source-frozen DIMACS CNFs and source SHA-256 checked before and after each trial. Same Ubuntu-24.04 GitHub runner, same selected single logical CPU, **serial (not parallel) launches**, deterministic shuffled 3-arm execution order for each source and repetition. Three repeats each; 4 original SHA x 3 arms x 3 repeats = **36/36** finished, all checked SAT witnesses from original CNF, no UNSAT and no timeouts. A 10-second nominal E2E cap per attempt; strict PAR2 uses original-SAT-verified completions, with 2x cap for unsuccessful attempts.

DRNAS R1 independently compiled from its own original C++17 source; its dynamic library check excludes all third-party SAT solver libraries. Kissat 4.0.4 and CryptoMiniSat 5.17 are separate, pinned SHA-verified reference *subprocesses only*, never linked into, copied into or called by the DRNAS native core. CMS uses one thread.

Timing definitions:
- `child_process_wall_s`: wall time from process launch through completion, including its internal DIMACS parse, solve, SAT output and operating-system launch overhead.
- `wall_E2E_with_original_model_check_s`: same process time plus independent Python replay of a SAT model on the **original CNF** and harness overhead.
- `child_CPU_s`: measured process CPU time via resource usage; separate from E2E and not confused with full-run wall time.
- For DRNAS only, inner `solver_s` is emitted by the native core; it is not substituted for full E2E.

This is a **previously selected development cohort conditional on DRNAS R3C plain successful SAT solving**, not a blind or representative SAT competition holdout. Conclusions below apply ONLY to these four selected original SAT cases.

## Same-runner matched results

Original SHA and **average E2E in seconds, 3 repetitions, 1 CPU**:

| SHA-256 prefix | DRNAS native R1 | Kissat 4.0.4 | CMS 5.17 | Fastest |
|---|---:|---:|---:|---|
| `5b874afeed91345a` | **0.004244** | 0.014057 | 0.046794 | DRNAS |
| `fc529dff1a6f763c` | **0.015144** | 0.037297 | 0.336625 | DRNAS |
| `907c98ebe3331af2` | **1.166294** | 1.620163 | 3.671599 | DRNAS |
| `92e5fa675073ba9a` | 2.453581 | 0.065757 | **0.060512** | CMS |

4 SHA x 3 reps = 12 attempts per solver; each arm 12/12 original witness verified.

| Arm | SAT verified | timeout | strict E2E/PAR2 total seconds | total process wall seconds | total child CPU seconds |
|---|---:|---:|---:|---:|---:|
| Kissat 4.0.4 | 12/12 | 0 | **5.211823** | 5.176616 | 5.146240 |
| DRNAS native R1 | 12/12 | 0 | **10.917790** | 10.883024 | 10.864291 |
| CryptoMiniSat 5.17 | 12/12 | 0 | **12.346589** | 12.311647 | 12.290378 |

**Matched ratio**: Kissat is 10.917790/5.211823 = **2.095× faster** than DRNAS by sum E2E/PAR2; DRNAS is 12.346589/10.917790 = **1.131× faster** than CMS by the same metric on this selected set. Both comparisons have 100% verified-SAT success and no timeout penalty. Three per-source DRNAS wins do **not** overturn the aggregate Kissat win because the fourth case (`92e5...`) dominates the difference.

## Decisions

- The own R1 standalone CDCL is functional and competitive on *some selected originals*, especially three sources where it has lower measured E2E than both established reference solvers in this matched test.
- The biggest optimization target is `92e5fa67...` where CMS completes in ~0.0605 s, Kissat ~0.0658 s but own R1 needs ~2.45 s. Profile trail, conflicts, propagation/watched-literal overhead, preprocessing and branching, not just GF2.
- Preserve this permanent four-SHA **nonblind DEV** set for regression, benchmark every candidate on the same runner and one CPU; for credible generalization use a separate unseen source-only preregistered original SHA cohort with original SAT model verification and independently checked UNSAT proofs.
- No foreign solver libraries integrated into DRNAS; no main branch edits.

## Source details
Full original SHA-256, in fixed dev order:
1. `5b874afeed91345a786ac4345c97aa3e617c57f748570be83421d149b34abebc`
2. `fc529dff1a6f763c97b0ed1dd33199e0d9dd26c50d210f9032e4fdaab5534c16`
3. `907c98ebe3331af203f0f9f67529e6933255cd1b0550ecc7caf9d4cdc35514a0`
4. `92e5fa675073ba9aad91afa4b81129fed5757ea37872fc2dbc3bd4ba0d720a4c`
