# DRNAS X4.5a: predict measured continuation work

X4.5a changes one polarity at native CDCL decision 4. It learns from paired
continuations of the same deterministic solver state. The target is
`log1p(base remaining propagations) - log1p(flipped remaining propagations)`;
it is not a clause-satisfaction proxy or a claimed mathematical SAT distance.

## Fixed protocol

- 768 new generated SAT formulas: 384 training, 144 validation, 240 holdout.
- 16 generator regimes (8/3/5), not 16 independent mathematical classes.
- Model, threshold and feature schema frozen before holdout outcomes.
- One logical CPU, 0.4 s end-to-end cap, 3 randomized-order holdout repeats.
- SAT witnesses checked against each original CNF outside the solver.
- Independent exhaustive small SAT/UNSAT correctness tests cover every policy.
- No changes to main, no APK, no foreign solver linked into the implementation.

## Policies

CORE preserves the original branching policy. SHAM computes identical learned
features/model scores but keeps CORE's decision. FIXED chooses polarity using
the weighted residual clause occurrence difference. FLIP always reverses the
selected decision. LEARNED uses a frozen nine-member ridge ensemble trained
on continuation work; an ensemble disagreement penalty and a train-scaled
feature guard can abstain. The score is not a calibrated probability.

The validation-only threshold grid includes disabling intervention entirely.
The baseline is not assumed inferior. There is no holdout-driven retraining.

## Evidence and limits

Primary outcome: paired holdout end-to-end PAR2 for LEARNED vs CORE. The
predeclared success criterion is a lower 95% formula-cluster bootstrap bound
above 10% improvement. The same comparisons against SHAM, FIXED and FLIP are
mandatory controls. All repeated trials are clustered by original formula;
an exploratory family-cluster interval is also reported, with only five
holdout regimes. These exploratory intervals are not multiplicity-adjusted.

Training and prediction metrics exclude pairs whose continuations do not
both finish and verify within the cap. Their exclusions are counted. Runtime
PAR2 includes every held-out formula, including timeouts and overhead.
Prediction metrics use nontrivial work differences (absolute log ratio >0.10).
The model acts once; its labels do not establish utility of repeated interventions.

Process startup and model loading may dominate these small formulas. Work
counts help distinguish search effects from timer noise but do not replace
end-to-end results. This is a mechanism experiment on generated SAT; it does
not establish industrial, UNSAT, or Kissat/CaDiCaL/CryptoMiniSat superiority.
Training/generation/verification costs are not amortized into solve speed.

## Reproduction

```bash
python3 -m pip install numpy==2.3.5
mkdir -p build
g++ -std=c++20 -O3 -Wall -Wextra -Wpedantic -Werror src/drnas_x41.cpp -o build/drnas-x41
g++ -std=c++20 -O3 -Wall -Wextra -Wpedantic -Werror src/drnas_x45a.cpp -o build/drnas-x45a
python3 tests/test_x45a.py --cases 400
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python3 -u research/drnas_x45a.py --out x45a_results
```

Artifacts include the frozen manifest and protocol, all paired training and
validation observations, the exact frozen model, per-formula holdout runs,
matched holdout diagnostic pairs, and the final report. Repeating this exact
manifest is a replication, not a fresh blind generalization test.

## Completed result, 2026-11-13

[GitHub Actions run 43357802267](https://github.com/Frane12/AndroidGameTest/actions/runs/43357802267)
completed successfully at source commit `dfc38a07dc4f6c0ed6b18ad3bab855af89e7f1b7`.
Independent correctness: 3,296 solver runs, 404 truth-table sources, 59 matched
intervention checkpoints, all tested policy paths valid and CORE unchanged.

Both the local run and the GitHub run selected the disabled-intervention
threshold using validation only. All five policies solved all 720 held-out
trials (240 original formulas, three repeats). No learned intervention was
accepted. CORE and LEARNED each used exactly 322,641 propagations in total.

GitHub holdout totals:

| Policy | PAR2 seconds | Accepted interventions |
| --- | ---: | ---: |
| CORE | 2.056987 | 0 |
| SHAM | 2.114356 | 0 |
| FIXED | 2.071618 | 135 |
| FLIP | 2.048247 | 720 |
| LEARNED | 2.110799 | 0 |

LEARNED vs CORE improvement was -2.616%, formula-cluster 95% interval
[-2.898%, -2.288%]. This measures overhead on tiny generated formulas, not
industrial SAT performance. The predeclared >10% success criterion failed.

Read-only post-hoc analysis (`research/drnas_x45a_diagnose.py`) gives held-out
ensemble-score AUC 0.4870, 95% formula-bootstrap interval [0.3963, 0.5784],
on 159 pairs with a nontrivial verified continuation-work difference. The
fixed disabled policy has balanced accuracy 0.5 by construction; its [0.5,0.5]
bootstrap interval is not evidence that the underlying predictor is known
exactly. Raw score AUC is the more informative discrimination diagnostic.

A perfect-information selector of the cheaper observed polarity would reduce
total propagation work by 22.043% on these held-out pairs. This is retrospective
headroom, not an achieved speedup or evidence that pre-action features can
recover that advantage cheaply.

Local execution agrees on failure of the learned policy (score AUC 0.4921,
no interventions, 3.716% measured overhead). The two fits are not bit-identical:
wall-time censoring admitted 340 local vs 359 GitHub training pairs. Both
followed the same frozen protocol, with no holdout-driven retuning. Future
training should use a deterministic search-work budget to reduce this bias.

Next experiment should keep the matched continuation label, add bounded
polarity-specific propagation features, test nonlinear feature interactions,
and use new harder family-separated formulas. Current holdout evidence must
be treated as development data after this analysis.
