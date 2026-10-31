# DRNAS NP Lab — NeuroFlow v0.6.1 two-stage experiment

**Research status:** experimental. This branch leaves established v0.6 untouched.

GitHub Actions: https://github.com/Frane12/AndroidGameTest/actions/workflows/drnas-neuroflow-v061.yml

## Why v0.6.1?

v0.6 used 17 structural features on *every* input even after its trained policy
set `disabled=True`. On independent external SATLIB data it slowed down rather
than speeding up the SAT solver: the controller paid for features which could
not change its decision. v0.6.1 fixes this specifically.

## Algorithm

- Global disable: immediately call the existing exact SAT solver, calculating
  **zero** extra structural features.
- Stage 1: single cheap literal pass recording signed-minority frequency,
  fraction of unit clauses, and problem size. Learn size and threshold gates
  from TRAIN data, not test data.
- Only if Stage 1 accepts: Stage 2 computes the previous 17-component
  structural vector and estimates Horn defect.
- If Stage 2 accepts: run exact renamable Horn recognition via 2-SAT.
  Accept only mathematically equivalent transform; solve using Horn;
  map satisfying assignment back to the original variable polarities
  and check the model. If unsuccessful, use the original exact solver.
- Each path has a wall-clock budget. No prediction of SAT vs UNSAT required
  for choosing transformations.

## Independent evaluation and safeguards

- 160 SATLIB instances from the v0.6 test become TRAIN data.
- A fresh 160 SATLIB instances, selected using a new fixed seed and
  **original file SHA-256 filtering against all SATLIB instances from
  v0.2 through v0.6**, become the independent held-out test.
- 72 separately generated renamable-Horn controls in each set.
- Train on 232 cases, freeze the chosen policy **before** inspecting the
  232 held-out cases.
- Compare original baseline, forced Horn attempt, previous v0.6 disabled
  policy (still computes 17 features), and new two-stage policy with
  three matched in-process measurements per held-out problem.
- GitHub runner, Python 3.12, real CryptoMiniSat for SATLIB status validation.
- Test assertions verify all four solver statuses match and all SAT
  assignments satisfy the original CNF.
- Record cheap stage, expensive stage, observed route, timings and
  source fingerprint; no fabricated CryptoMiniSat speed claim.

## Interpretation

A faster two-stage policy on *constructed* Horn examples would demonstrate
successful selection in that domain. It does not establish a better
general-purpose SAT solver or P=NP. A policy that disables every probe
is correct if the expected benefit does not exceed its overhead; unlike
v0.6, v0.6.1 does not charge expensive feature costs in that case.

The new threshold grid is trained only on train data. Search over threshold
grids can overfit; the final independent holdout is the relevant test.
