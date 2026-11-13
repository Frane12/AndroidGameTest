# DRNAS X4.4 Guarded Memory — first completed test (2026-11-13)

Branch: experiment/drnas-x44-guarded-memory-20261113
GitHub Actions run: https://github.com/Frane12/AndroidGameTest/actions/runs/43354506630

## Aim

Can a formula/family-balanced binary predictor, genuinely continued across
three cumulative training cycles, and an out-of-distribution (OOD) abstention
gate make reliable BEFORE-action predictions of the direction of the
exhaustively measured SAT-completion probability?

The native X4.2 CDCL solver is unchanged and never reads a model prediction.
This is an **offline** predictive diagnostic, NOT a new active SAT heuristic.

## Data and correctness

- 288 distinct SAT training CNFs from 6 generator families; three learning
  cycles with 96 additional independent originals in each cycle.
- 64 distinct validation CNFs from 4 different generator families.
- 128 **new, held-out** SAT CNFs from four generator families that were newly
  introduced for this test: hub4_planted, modular2_3, ring3_planted, xor_fan.
- 16 independent original UNSAT controls from php_unsat and graph_k4_unsat,
  both exhaustively checked by complete enumeration.
- 496 SHA-distinct original CNFs total, three variable-renamed search replays
  each, i.e. 1488 native runs. Replay/decision rows are not independent
  source formulas. All credited SAT witnesses checked against original CNF.
- 1461 nonflat (away/toward) labeled holdout decision events.

## Training details

The model reuses coefficients across cycles, mapping weights when the
training-only feature scaler changes so that the old decision boundary is
preserved mathematically before gradient updates. It fits a family- and
source-balanced binary logistic loss on nonflat decisions only.

| Cycle | New cumulative original training sources | Validation away-risk AUC |
| --- | ---: | ---: |
| 1 | 96 | 0.6444 |
| 2 | 192 | 0.6469 |
| 3 | 288 | 0.6559 |

Validation chose the final cycle-3 checkpoint with risk threshold 0.40,
uncertainty margin 0.04, OOD threshold 1.60. Validation before-action
nonflat prediction covered 86.65% of events and achieved 66.13% balanced
accuracy among accepted events (away recall 81.12%, toward recall 51.14%).

## Fresh holdout outcome — NEGATIVE

**The predicted signal failed to generalize. Do not activate this policy.**

- Away-risk AUC on holdout: **0.5319** (close to chance 0.5).
- Prediction coverage on nonflat events: **82.14%**.
- Balanced accuracy among accepted: **52.28%**;
  95% formula-cluster bootstrap CI **[49.43%, 54.93%]** includes chance.
- Away recall among accepted: **94.31%**.
- Toward recall among accepted: **10.25%**.
- Precision of emitted away warnings: **37.74%**.
- OOD abstentions: 42; low-confidence abstentions: 219.
  In particular, the OOD detector abstained on only 42/1461 = 2.87% of
  nonflat events despite the held-out families being entirely different.
- Unprotected 3-class models had poor away AUC on this same holdout:
  early20 softmax 0.4634, ridge010 softmax 0.4866.

### By held-out family

| Family | Original CNFs | Nonflat events | AUC | Coverage | Accepted balanced accuracy |
| --- | ---: | ---: | ---: | ---: | ---: |
| hub4_planted | 32 | 530 | 0.5422 | 81.70% | 51.70% |
| modular2_3 | 32 | 199 | 0.5487 | 90.95% | 51.07% |
| ring3_planted | 32 | 540 | 0.5459 | 84.07% | 53.17% |
| xor_fan | 32 | 192 | 0.5104 | 68.75% | 50.00% |

## Interpretation

1. **Warm-start training is technically possible**: we implemented persistent
   coefficients with an exactly transformed scaler, rather than retraining
   from initial random weights each cycle.
2. It did not solve transfer to unrelated structural distributions.
   Validation AUC improved mildly across cycles but holdout AUC fell to ~0.53.
3. A classifier can have high recall for away by overpredicting "away".
   That gives very poor recall for genuinely positive actions.
4. A simple global OOD cutoff does not reliably identify structural
   novelties, and abstention itself cannot be called a successful learned
   heuristic when risk quality is near chance.
5. The target is still a retrospective conditional SAT-completion probability.
   It is neither a causal counterfactual outcome nor a guaranteed proxy for
   remaining CDCL runtime. Improving target prediction is not equivalent to
   shortening proof/search time.

## Promotion gate

Keep X4.4 **shadow/offline only**. Do NOT integrate it into active CDCL
variable selection, learned-clause generation or UNSAT certification.

A worthwhile next experiment would measure matched-state, proof-safe
short continuations (where feasible), target actual verified time/conflict
cost rather than Hamming or conditional solution fraction, and test a
calibrated risk model at fixed coverage on genuinely untouched families.
For large industrial CNFs, avoid exponential truth-table enumeration.
No new claims about solver speed, NP-completeness or P=NP are supported.

The run artifact contains manifest, frozen models, all holdout predictions
and the complete report. The root branch remains unchanged.
