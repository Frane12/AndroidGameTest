# DRNAS X4.3: before-action prediction — completed experiment (13 November 2026)

CI run: https://github.com/Frane12/AndroidGameTest/actions/runs/43350075238

## Protocol

- Native X4.2 engine was unmodified and its decisions received **no** input
  from the prediction model. This is an OFFLINE shadow prediction test.
- 288 **distinct original CNFs for training** from four generator families,
  24 originals per family at each of three consecutive training cycles.
- 24 original validation CNFs from the separate sparse4 family, evaluated
  after each cycle; not used for training, scaling, or selecting hyperparams.
- 64 **never-used-in-training** holdout CNFs from two further generator families:
  32 sparse3 and 32 xor_ring. Each source had 3 representation replays.
- 16 independently exhaustively checked UNSAT control CNFs. The model never
  invents a toward/away label for UNSAT.
- Total: 392 SHA-distinct original CNFs, 1176 replay runs; 1932 labelled
  holdout decision steps. The independent unit is 64 original CNFs, NOT 1932
  events and NOT 192 replays.
- The supervised label was determined **after** solving from an independent
  exhaustive enumeration of all SAT assignments at n <=18. The model only
  saw pre-action CDCL state, the action literal, static formula features and
  preceding already-observed events.
- No real-world SAT Competition solver speedup is tested or established.

## Three learning cycles (the same separate validation formulas)

| Cycle | Cumulative distinct train CNFs | Model formula-mean log loss | Constant model log loss | Nonflat direction accuracy |
|---|---:|---:|---:|---:|
| 1 | 96 | 0.9304 | 1.0798 | 69.01% |
| 2 | 192 | 0.8558 | 1.0771 | 69.01% |
| 3 | 288 | 0.9926 | 1.0785 | 69.01% |

The cycle-2 improvement REGRESSED in cycle 3, so **learning was not
monotonically convergent** on validation. Directional accuracy did not
improve with more training. The softmax hyperparameters were held fixed.

## Frozen holdout, two unseen training-family types

- Formula-mean model log loss: 0.9489947401.
- Formula-mean constant training-frequency baseline: 1.0810730820.
- Difference baseline minus model: +0.1320783419.
- 95% formula-cluster bootstrap CI for log-loss improvement:
  **[+0.09405,+0.17050]**. This supports a log-loss / distribution
  prediction improvement on the two held-out synthetic families.
- Three-class raw accuracy model 51.60%, constant majority guess 43.53%.
- For the **1131 NONFLAT toward-or-away events**, the model predicted the
  sign correctly on 75.15% versus 74.36% for always predicting the
  training-majority sign. Raw gain only **+0.80 percentage points**.
- This is NOT a robust gain in sign accuracy: an additional posthoc
  source-cluster bootstrap (7000 draws) yielded a 95% interval for
  sign-accuracy difference of approximately **[-1.52,+3.25] percentage
  points**.
- Away-class detection: 40/290 = **13.79% sensitivity**; toward:
  810/841 = 96.31% recall in the binary toward-vs-away aggregation,
  while away recall is 13.79%.
  The resulting balanced sign accuracy is about 55.05%. Posthoc
  formula-cluster bootstrap 95% interval for improvement over random
  balanced 50% is about [+1.77,+8.46] points.
- Classification is asymmetrically biased toward predicting positive
  steps. This small balanced-accuracy gain does NOT make the model a safe
  action selector.

By holdout family:

| Family | Distinct CNFs | Model mean log loss | Constant log loss | 95% logloss improvement CI |
|---|---:|---:|---:|---:|
| sparse3 | 32 | 0.81355 | 1.04442 | [+0.19305,+0.26783] |
| xor_ring | 32 | 1.08444 | 1.11773 | [-0.01048,+0.07652] |

The positive pooled result is mostly driven by sparse3; there is no
confirmed gain within xor_ring alone. A further genuinely fresh
out-of-family confirmation is required before treating these observations
as a general-purpose directional predictor.

## What is actually established?

1. We can create pre-action features, independently label outcomes after
   execution, train sequentially, freeze and test on new formulas.
2. The model has *some statistical information* about the distribution of
   immediate future outcomes, beyond a global train-frequency baseline.
3. It does **not** yet consistently tell which action truly moves toward SAT
   or improve along successive training cycles.
4. It has not chosen any solver decisions; no SAT/UNSAT speedups, causal
   improvements, complexity-theoretic conclusions or new mathematics can be
   claimed from this experiment.

The next algorithmic test should prioritize identifying away-events,
decision-conditioned counterfactuals and overhead, using truly untouched
families and independent SAT/UNSAT certificate checks.
