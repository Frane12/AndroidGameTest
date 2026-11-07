# DRNAS R15 — early trajectory vs single snapshot

Registered **2026-11-02** before creating any R15 run result. The frozen
V15.3.1 solver, R14 binary patch and all historic measurements remain unchanged.

## New approach
R14's early snapshot (at conflict 512) matched some extreme wins in R13
but FAILED independent R14 holdout: on 60 prospective Random3-SAT test formulas,
dual50 had PAR-2=84.403 seconds vs 83.072 monitor (-1.60%; 95% CI includes
zero); the R13 rescue50 baseline was 82.254 seconds (+0.98%, CI includes
zero). A handful of similarly scored instances had opposite response signs.
This motivates measuring **movement of the search system**, not one threshold.

Unlike R11–R14, R15 does NOT fit or bake a new C-side live restart heuristic.
R15 collects the same input and output under several fully measured restart
arms and uses pre-intervention checkpoint trajectories to predict which
arm would have performed better. Training/test separation is strict, and
counterfactual evaluation is honestly marked as **off-policy replay**,
not a deployed adaptive solver timing.

## Before-outcome measurements

On *unchanged same-binary* monitoring and forced arms, existing R11/R14
read-only R6_TRACE samples at 32,64,96,128,192,256,384,512,768,1024 etc.
We use only 128,256,512,1024 and the early 512-conflict observation.
All are strictly before restart intervention at conflict >=2048.

**Snapshot comparator:** n/240, variable degree CV/Gini, polarity imbalance,
early propagation ratio p512, early glue ratio g512, log restarts by 512,
learned clause rate by 512, stable mode, reached1024.

**Trajectory comparator:** all snapshot features plus interval-by-interval
propagation rates p[128,256], p[256,512], p[512,1024]; first and second
differences (acceleration / jerk-like discrete curvature);
glue ratios at 128, 256, 1024 and their first/second changes;
restart rates between [256,512],[512,1024]; learned clause rates over
same intervals and decision rate [512,1024].
All features and the transformations are frozen by
`experiments/drnas_v16/r15_frozen_protocol.json`.
Falling short of 1024 conflicts means **abstain**, not a fabricated zero
signal deciding on a policy.

## Prospectively collected measured SAT outcomes

Eight fixed modes, with randomized **order** across three repeats of each CNF:
1. `monitor`: same-binary passive reference, no altered restarts
2. `r11_2048_25`: forced change to native restartint=25 at conflict 2048
3. `r11_2048_50`: forced restartint=50 at conflict 2048
4. `r11_4096_25`: timing control, too late for the 1024 features to leak
5. `r13_rescue50`: frozen previous rescue heuristic
6. `r14_dual50`: frozen previous dual heuristic (R14 reference only)
7. `original_kissat`: unpatched upstream ref; separate instrumentation
8. `stable_v1531`: untouched V15.3.1; separate architecture

160 **new** formulas, deterministic independent generator seeds:
* Random3, n=200/220/240, clause density 4.23: 60 development + 60
  reserved test, 120 formulas total (16 unrelated previous dev/test groups
  are prohibited from training and held-out reuse).
* Community3, n=220/240, 65% within one of four variable communities:
  20 development + 20 reserved transfer-test, 40 formulas total.
  Synthetic community3 is NOT external official SAT Competition data.
* 16 job shards x 10 formulas x 3 repeat x 8 arms =
  **3840 independently executed SAT attempts**.
* Seed streams include 715150000 base, n*10000 and fixed fold / community
  offsets. All SHA256 input identities audited against a frozen
  **1934-element** historical formula registry through R14.

Every within-formula comparison runs on the same pinned CPU/runner and same
CNF and all 8 mode candidates, with 12s timeout per invocation, PAR-2=24s
if timed out. Monitor/patched native arms must have **identical checkpoint
counters through conflict 1024** (propagations, restarts, decisions, learned
clauses, glue ratio, stable state), before ANY intervention.
Provenance: input formula SHA256, generator seed, runner and CPU, source SHA,
Kissat pin, reference source blob SHA, compiled executable SHA, raw logs,
status, wall/cpu time, check SAT witness and reject contradictions.
UNSAT results are **not independent proof certificates**.

## Locked learning and evaluation protocol

Feature extraction uses only **monitor replicate #0** up to conflict 1024
(one observation per formula) and never uses future solver outcomes as
features. All three paired treatment repeats provide independent outcomes.

Two prespecified ridge regressors per feature-set (one predicting log ratio
of monitor vs forced25, another vs forced50).
* Training corpus: ONLY 60 R15 `random3_development` formulas (and only
  formulas which reached the 1024-conflict observation).
* Standardization mean/std from development only, standardized values
  clipped in [-3,3]; ridge penalty lambda 30, unpenalized intercept.
* Regression targets clip log(PAR-2 monitor / PAR-2 treatment) to [-2,2].
* Prediction: choose the policy with highest predicted log gain among
  forced25/forced50 if gain >0.12 (approximately 13% projected speedup)
  otherwise **monitor**.
* New reserved R15 `random3_test` and new `community3_test` receive the
  **same** locked model; no refitting or changing thresholds after seeing
  results. Retrospective community3 development is reported separately.
* Never use R15 test fold results to pick which model is better and report
  it as preselected; snapshot and trajectory are BOTH declared comparators.

**Primary endpoint**: formula-block bootstrap 95% CI of replay total
PAR-2 gain vs monitor on 60 prospective random3 test formulas, reported
separately for snapshot and trajectory, plus their paired difference,
chosen-mode counts, high-impact wins and regressions. Compare against
measured always-forced modes, previous gates and frozen references.
**Secondary**: 20 community3 held-out test formulas, by-size
subgroups and cases where trajectory vs snapshot decisions diverge.

An optimistic-looking replay is not proof that the live adaptive policy
runs faster: the replay borrows the already measured full solve of the
selected arm; it does not include actual runtime model inference overhead,
branch behavior or deployment effects. A genuine frozen R16 live
same-binary test on yet-new independent CNFs would be necessary to confirm.

The 1934 historical hashes only guarantee non-overlap with OUR frozen
archived corpus, not global uniqueness of 3-SAT formulas.
No official world-record, P vs NP or physical law can be claimed.
