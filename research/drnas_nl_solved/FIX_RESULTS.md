# AND-prior repair: original solved-formula replay

The experimental static AND-occurrence bonus sent all nine selected Simon instances into an unproductive search prefix. The repair removes that bonus entirely, preserves the CDCL priorities and phases, and retains the previously tested in-place clause preparation. This is a corrective rollback of the branching experiment, not a new mathematical pruning method.

## Implementation

- New executable: `build/drnas-nl-fixed`; the earlier executable and frozen references are unchanged.
- Default `--nl-focus fixed`: in-place preparation, no AND scan and no structural priority bonus.
- `--nl-focus observe`: recognize exact signed AND definitions and report their count without changing scores, phases, constraints, or decisions.
- `--nl-focus base`: same-executable baseline control. `inplace` remains a compatible preparation-only mode.
- Old experimental `inputs` and `both` options fail explicitly in the new binary; the preserved old executable remains available for retrospective investigation.
- `blocked_prior_variables` counts variables that the removed heuristic would have boosted. It does not count pruned branches. No branch is pruned by this repair.

## Verification and protocol

- Local execution, one logical CPU (CPU 0), one serial solver process; this report is not a GitHub Actions run.
- Same original bytes and source hashes: nine AND-certified Simon CNFs plus the previously selected five transfer controls (two easy, three medium). The five transfer controls are not AND-filtered.
- 10 measured repeats, four arms (BASE, FIXED, Kissat, CaDiCaL): **560/560 verified**, 480 SAT models and 80 checked UNSAT DRAT proofs. No timeout or incorrect result; 56/56 additional warmups verified.
- BASE/FIXED are adjacent in alternating order; source order is deterministically shuffled. Native arms use the same repaired binary with COOP4/5 off. Solver cap 5 s, independent checker cap 25 s.
- All 140 native pairs have identical decisions, conflicts, propagations, learned-clause and restart counters; all 120 SAT model pairs and 20 UNSAT proof pairs are byte-identical.
- Separate validation: 204/204 checks on 68 exhaustive-oracle small cases; 27/27 real replays across frozen BASE, repaired default and observational recognition. All nine real formulas use 32 decisions and zero conflicts. Sampled decision traces and complete output models match the frozen baseline.

## Timing

Simon sum of per-source medians: BASE 61.298 ms, FIXED 52.917 ms, a 13.67% reduction. Including independent checking, the reduction is 7.20%. This gain comes from the retained preparation optimization, not improved search.

The three medium formulas sum to BASE 4.102653 s and FIXED 4.101091 s (0.038% reduction). Each medium instance's paired repeat bootstrap interval includes zero: **no demonstrated medium-instance speedup**.

Median solver-process wall time in milliseconds; includes launch, parsing, solving and model/proof output, excludes the independent checker. Positive reduction favors FIXED.

| Original | BASE ms | FIXED ms | Kissat ms | CaDiCaL ms | Reduction |
|---|---:|---:|---:|---:|---:|
| simon-r16-1.sanitized.cnf.xz | 6.323 | 5.283 | 4.671 | 5.756 | 16.45% |
| simon-r17-0.sanitized.cnf.xz | 6.148 | 5.514 | 4.461 | 6.571 | 10.32% |
| simon-r18-0.sanitized.cnf.xz | 6.447 | 5.728 | 5.082 | 7.316 | 11.15% |
| simon-r19-1.sanitized.cnf.xz | 6.391 | 5.702 | 4.923 | 6.404 | 10.79% |
| simon-r20-0.sanitized.cnf.xz | 6.568 | 5.616 | 4.952 | 7.161 | 14.50% |
| simon-r21-0.sanitized.cnf.xz | 7.123 | 5.681 | 5.435 | 7.751 | 20.24% |
| simon-r22-1.sanitized.cnf.xz | 7.067 | 6.341 | 5.417 | 7.485 | 10.28% |
| simon-r23-1.sanitized.cnf.xz | 7.130 | 6.103 | 5.374 | 7.458 | 14.40% |
| simon-r24-1.sanitized.cnf.xz | 8.100 | 6.950 | 5.579 | 7.957 | 14.20% |
| Break_unsat_04_03.xml.cnf.xz | 8.295 | 8.513 | 17.572 | 8.003 | -2.62% |
| worker_20_40_20_0.95.cnf.xz | 8.330 | 7.993 | 38.688 | 77.842 | 4.04% |
| Break_unsat_06_07.xml.cnf.xz | 3789.438 | 3792.775 | 628.949 | 596.633 | -0.09% |
| ITC2021_Early_3.xml.cnf.xz | 240.801 | 237.120 | 222.275 | 163.921 | 1.53% |
| Break_08_24.xml.cnf.xz | 72.415 | 71.196 | 72.166 | 406.749 | 1.68% |

Kissat remains faster in the aggregate of these 14 sources. The repair restores the successful baseline search; it does not establish superiority over reference solvers. The previous r16 bad-prior 4.93 s UNKNOWN and nine 100 ms diagnostic UNKNOWN traces are censored historical observations, not exact runtimes or a speedup denominator.

This is a retrospective regression replay, not blind holdout. The nine nonlinear examples are one Simon family, and there are only three medium transfer examples. No promotion to main is justified by this result.

## Reproduction and retained evidence

Build the frozen DELTA4X source, then run `research/drnas_nl_solved/build.py`, `build_fix.py`, `validate_fix.py`, and `bench_fix.py --reps 10`. The manual `.github/workflows/drnas-nl-fixed.yml` restores the original artifacts, validates hashes, compiles, checks results, and retains generated proofs and logs. It was prepared but not dispatched for this local replay.

Committed evidence: `fixed_report.json`, `fixed_protocol.json`, `fixed_build.json`, `fixed_validation.json`, `fixed_trials.jsonl.gz`, `fixed_warmups.json.gz`, `fixed_raw_logs.json.xz`, `fixed_validation_traces.json.gz`, and compiler identification. Raw-log JSON maps filenames to their text. Trials retain proof and model SHA-256 values; large DRAT files were checked locally and are regenerated by the replay workflow.

Code commit: `c5e32c7640d21226b462d5d7c5d4f4e089e40c51`.
