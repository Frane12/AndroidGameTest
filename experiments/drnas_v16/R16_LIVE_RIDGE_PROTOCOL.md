# DRNAS SAT R16 — real live frozen R15 trajectory model in pinned Kissat

Registered **2 November 2026**, before any R16 generated test result.
Branch: `experiment/drnas-r16-live-frozen-ridge50-20261102`.

## Why R16 and what we are testing

R15 measured 3840 real SAT executions and tested its ridge predictor only via
**off-policy replay** (selecting between already-recorded monitor and forced
restart arms). R15 trajectory replay gained +1.10% total PAR2 on 60 novel
Random3 test cases but its formula-bootstrap CI included zero; it also
introduced three >2x regressions. The simple snapshot replay gave -2.89%.
R15 is *not* evidence of a successful live adaptive algorithm.

R16 tests for the **first time the actual trained model executing INSIDE
one continuously solving Kissat process**. It computes a prediction at
conflict 1024 using only preceding search behavior, then chooses whether
to modify the native restart interval at conflict 2048. No second
monitor solve, re-run, retrospective oracle, learned-clause reset or
knowledge of SAT outcome is available to the model.

## Native code and frozen trained model

- Upstream pinned Kissat commit: `8af8e56f174b778aef3aa45af9f739b2a5f492c2`
- Immutable original V15.3.1 file Git blob:
  `d280a2ffa28d72aec183323bbea40544d676112d`
- R15 trained model Git blob:
  `d005747f177008172b49cef5f0b8a6f29c3ffc46`.
  Only **59 eligible Random3 development** formulas contributed to its
  frozen regression weights. No R16 data and no R15 test data refit
  weights; R15 test observations are historical context, not R16 proof.
- Native instrumented source is R14 pinned patch + R16 add-on:
  `experiments/drnas_v16/patch_r16_live_ridge.py`.
- At conflicts 128,256,512,1024 store exact cumulative propagations,
  decisions, restarts, learned clauses, glue ratio and stable state.
  Capture R15-style 512-conflict p and g (from original logged
  DRNAS_V177_EARLY). Input CNF occurrence-degree CV/Gini, positive/
  negative polarity imbalance, and n are fixed *before* solving.
- The frozen R15 model has **25 trajectory features** and ridge
  coefficients for predicted `ln(PAR2_monitor/PAR2_forced50)` along with
  the 10-feature snapshot model. Native C exactly reproduces R15
  standardization, clip [-3,3], and coefficient multiplication. Its
  C score/choice must agree with Python numeric reconstruction from the
  native solver's own logged trace within 2e-5 absolute.
- Only n>=220 may intervene (conservative risk guard). Select
  restartint=50 only if complete checkpoints and model score exceeds
  the frozen threshold. Otherwise leave the running solver alone.
- Main `r16_live50`: threshold **0.25** on frozen trajectory50 score.
  Secondary strict `r16_live50_strict`: threshold **0.40**.
  Snapshot comparator `r16_snapshot50`: threshold **0.25**, same
  eligibility but only one 512-conflict snapshot. None may choose
  restartint=25. All three are now truly **live** policies.

The thresholds were selected with R15 exploratory development and
conservative risk principles. The history through R15, including its
already consumed test, is prior hypothesis-generating work; the **new R16
test fold is the first independent prospective test of this native
implementation**. If we change a threshold after inspecting new R16
test outcomes, the revised result needs a yet-new blind holdout.

## Experimental controls, provenance and validity

10 fully measured modes on exactly the same formula and pinned CPU:
1. `monitor` (same compiled instrumented Kissat, passive)
2. `r11_2048_50` (unconditional native restartint=50 at 2048)
3. `r11_2048_25` (unconditional restartint=25 at 2048)
4. `r13_rescue50` (frozen historical selective control)
5. `r14_dual50` (frozen historical selective control)
6. `r16_live50` (primary real live frozen learned trajectory)
7. `r16_live50_strict` (stricter threshold)
8. `r16_snapshot50` (one-snapshot live model)
9. `original_kissat` (unpatched reference, different instrumentation)
10. `stable_v1531` (unchanged baseline, different architecture)

All but the last two use one identical compiled native Kissat executable.
References are **not** same-binary causal comparisons.

**160 new prospectively generated 3-CNF**:
- 120 fresh Random 3-SAT formulas, n=200/220/240 at density 4.23,
  60 development + **60 reserved test**; two shards of 10 per n and fold.
- 40 separate synthetic community3 formulas, n=220/240, 65% of clauses
  within four variable communities, 20 development + **20 reserved test**;
  separate transfer metrics, not official competition datasets.
- New deterministic base seed 816160000. Check that 160 new SHA256
  identifiers are distinct and do not overlap the immutable 2094
  R7–R15 history entries. This does not establish novelty against the
  entire universe of formula collections.

3 attempts for each formula/mode, shuffled reproducibly, with all modes
for each formula on the **same pinned CPU/runner**. Exactly
**160 x 10 x 3 = 4800 real native solves**. Timeout 12 seconds per
attempt, PAR-2 penalty 24 seconds. Do not compare raw times across
different hardware as if paired. Store repository commit, source and
binary SHA, runner/core, input SHA/seed, SAT/UNSAT status, verified SAT
witness, wall/cpu times, R6_TRACE and R16_DECISION, actual switch
event/interval, before/after learned-clause count.

The run immediately fails if C/Python score or choice disagrees; if
the chosen intervention occurs before 2048, uses anything except
restartint=50 or changes learned clauses; if a short formula emits an
unexpected choice; if SAT answers conflict or a SAT assignment is
invalid. At aggregation, require exact 16 complete 300-row shards,
4800 unique attempt identities, 160 formula SHA identities,
repetitions, same runner per paired group and IDENTICAL monitored
counters through conflict 1024 for every in-binary comparison. No
claims of independent UNSAT proof: raw Kissat output is not an
independently verified certificate.

## Primary scientific endpoint

On only the **60 R16 random3_test** formulas: real-live R16 model
total PAR-2 vs same-binary monitor, in seconds and percent, 95%
bootstrap confidence interval resampling entire formulas stratified
by n, gain/regression counts >2x, native decision count and actual
restart count. Threshold 0.25 policy is PRIMARY; strict and snapshot
are predeclared controls. Secondary: comparison against force50,
frozen R13, R14, community transfer, and type/size subgroups.

Improvement is not statistically established if the CI includes
zero. Even a statistically positive result on new synthetic 3-SAT
would not imply worldwide SAT Solver ranking, polynomial-time
algorithms, P=NP, or proof of all UNSAT instances. External official
benchmarks, independent verified UNSAT certificates and reproducible
different-hardware runs would follow only if R16 passes.

The V15.3.1 and previous branches stay unmodified, and no R16 data
is merged into the cumulative analytics database until its own
fully verified completed artifacts are available.
