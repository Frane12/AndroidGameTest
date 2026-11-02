# DRNAS R16 — frozen-model decision error analysis

Read-only audit of frozen run 41426664482.
Input commit c31a02578ff0f98a9dabe8325e9b01392e13be10, frozen source git hashes explicitly checked.
No solver changes, no retraining, no adapted thresholds, no new holdout claim.

## Primary random3 test — same formula & runner

| Scope | CNFs | Monitor PAR-2 | Forced50 | Live50 | Selected | Missed beneficial | Selected harmful |
|---|---:|---:|---:|---:|---:|---:|---:|
| random3_test | 60 | 92.779234 | 91.049533 | 93.003195 | 11 | 26 | 5 |
| random3_test_n200 | 20 | 15.126437 | 13.727577 | 15.249874 | 0 | 12 | 0 |
| random3_test_eligible_n220_240 | 40 | 77.652797 | 77.321956 | 77.753321 | 11 | 14 | 5 |
| random3_test_n220 | 20 | 18.541322 | 20.87649 | 18.642229 | 5 | 6 | 3 |
| random3_test_n240 | 20 | 59.111475 | 56.445466 | 59.111092 | 6 | 8 | 2 |

## Key failure modes

1. **Eligibility exclusion:** n=200 cannot be selected, even if independently measured forced50 is faster.
2. **Weak ranking:** on 40 eligible random3_test CNFs, formula-level Spearman=0.0595, AUC=0.59, bootstrap 95% Spearman CI=[-0.2784, 0.3954].
3. **Harmful high scores:** model selects some formulas with measured severe regressions.
4. **Missed beneficial low scores:** model declines some formulas with real measured 2048/50 gains.
5. **Policy vs observed overhead:** selected live and forced50 differ slightly despite same restart interval; don't equate the two timings mechanically.

## Candidate future experiments (NOT implemented or optimized here)

- Fit error/risk model on development formulas only (new split), validate on new untouched SHA cohort.
- Preserve unmodified V15.3.1, R16 model SHA, fixed decision at 1024, action at 2048.
- Add a conservative abstention decision, uncertainty/robustness margins and counterfactual diagnostics *before* evaluating on fresh formulas.
- For n200, run a separate PREDECLARED eligibility ablation rather than silently changing the R16 primary rule.
- Collect more conflict trajectories and quantify solver-time overhead; no proof of an invariant universal jerk law.

## Provenance

R16 generated Random3-SAT/Community3-SAT. SAT witnesses were checked by existing R16 code;
independent UNSAT certificates were not checked. The historic test is now exploratory for any new rule.

See diagnostics.json for exact scores, source hashes, measured cases and risk breakdown.
