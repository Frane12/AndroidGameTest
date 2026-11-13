# DRNAS X4.3 — why adding more training did not solve direction prediction
Date: 2026-11-13. Research diagnosis, not an accepted native SAT improvement.

## 1) The demonstrated failure: source-distribution mismatch + overfitting

In X4.3, the model is a 28-feature, three-class ridge softmax learner. Every
cumulative cycle *refits its weights from zero*, over an enlarged training set.
It is not persistent weight-continuation between cycles. The policy is OFFLINE:
none of the learned scores are used to control native CDCL decisions.

Validation was one source-family-disjoint cohort of sparse4 formulas. Its
clause-density feature (clauses/(8*nvars)) averaged 0.1259, compared with 0.6326
on 288 training sources (~5x difference). Relative decision depth averaged
0.4415 versus 0.0881 in training. Hence many test states lie in a very
different structural regime from the training distribution.

The class distribution in new training slices was relatively stable:
away fraction 27.8%, 26.7%, 26.7% over cycles 1/2/3. Class-rate drift alone
does NOT explain the validation regression.

## 2) Same 288 training formulas, varying optimization epochs

| Epochs | Train formula-mean log-loss | Validation formula-mean log-loss |
|---|---:|---:|
| 20 | 0.8875 | 0.8250 |
| 45 | 0.8822 | 0.9052 |
| 60 | 0.8809 | 0.9417 |
| 90 (former default) | 0.8793 | 0.9926 |
| 180 | 0.8772 | 1.0676 |
| 360 | 0.8757 | 1.1231 |

As the training objective improves, transfer performance deteriorates. This
is strong evidence of **training-source-specific fit / overfitting**, not
proof that extra epochs are universally harmful.

A stronger ridge penalty also helped on the old validation: 90 epochs with
ridge 0.1 produced 0.8320 loss, versus 0.9926 with ridge 0.014. A model
with fewer free parameters or stronger distribution-invariant features
deserves further testing.

## 3) The model can rank some negative steps, but is not well calibrated

On old 24-source validation, away AUC was ~0.836 after cycle 2 and ~0.835
after cycle 3. Yet the default three-class argmax predicted **zero** of
220 truly away steps as away. A better ranking score is not the same thing
as a useful action decision.

The threshold selected to maximize direction-balanced accuracy on that
validation family did not reliably transfer to other structures.

## 4) Prospective confirmation on THREE genuinely new generator families

Workflow:
https://github.com/Frane12/AndroidGameTest/actions/runs/43352896161

108 original SAT CNFs (36 per family): planted4_dense, xor_bridge,
mixed_sparse_23; each source has three correlated, variable-renamed replay
trajectories. All SAT answers externally checked on the original CNF;
model files frozen before these holdout outcomes were observed.

| Candidate | New-source formula-mean log-loss |
|---|---:|
| cycle2_90 | 0.9764 |
| cycle3_90 | 0.9768 |
| cycle3_early20 | 0.9510 |
| cycle3_ridge010 | 0.9411 (exploratory secondary) |

Predeclared comparison: early20 vs cycle3_90: +0.0258 log-loss improvement,
paired formula-bootstrap 95% CI [+0.0035,+0.0487]; family-cluster CI with
only three held-out families [-0.0189,+0.1024]. The family-level interval
includes zero. Do not claim universally transferable improvement.

**Direction threshold still fails**: a validation-selected threshold 0.15
recognized virtually all away steps in this new cohort, but only 3.1% of
toward steps. Balanced accuracy was ~51.6%, barely above a 50% one-sided
baseline; despite training more sources, the directional controller remains
inadequate.

The fresh-family ROC-AUC for away was ~0.691 (early20), down from ~0.80 on
the previously inspected X4.3 holdout. This is an out-of-distribution
weakness, not proof of mathematical understanding.

## 5) A deeper issue: the target itself is not computation cost

The exhaustively calculated probability that a random completion of the
current partial assignment satisfies the CNF is NOT a verified measure
of remaining CDCL runtime or a causal benefit of a chosen branch.
An apparently away step can still find SAT cheaply or establish UNSAT via
backtracking and proof. More training against the same surrogate cannot
eliminate target mismatch.

## Next scientifically justified development

1. Explicitly detect unfamiliar formula/search features and abstain,
   retaining ordinary CDCL rather than acting on fragile predictions.
2. Use source-family-balanced training, source-weighted normalization,
   early stopping, stronger regularization and held-out calibration.
3. Predict away separately and evaluate precision, recall, balanced accuracy
   and calibration on multiple untouched structural families.
4. Evaluate policy changes only in costed paired runs (same CNF/seed,
   independent checks); verify SAT witnesses, certify general UNSAT proofs,
   report solved count and end-to-end PAR2.
5. Do not treat multiple replay cycles or correlated transitions as
   independent formulas. Log-loss improvements alone cannot promote a
   learned branching policy.

Artifacts include frozen model versions, validation-selected thresholds,
all fresh predictions and the paired confidence report.

This is an experimentally useful negative result with a partial probabilistic
prediction improvement. A reliable learning-based SAT kormilar is **not**
established yet.
