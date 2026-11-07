# DRNAS SAT R11 — frozen restart timing and intensity causal sweep

**Preregistered: 2026-11-02.** Strictly experimental. Do not modify or
replace the V15.3.1 frozen solver or proven production heuristics.

## What is already known
R7 development generated random 3-SAT shows extreme within-Kissat paired
changes (27.68x and 27.10x on isolated formulas) under a switch at conflict
2048 to restartint=25, but also serious regressions on matched neighbors.
The R10 gate used only degree CV/Gini; its 60-case held-out gate improvement
was +1.24% total PAR-2 with formula-block bootstrap 95% CI containing zero.
Original Kissat and frozen V15.3.1 are not the exact in-process causal control.

## Frozen hypothesis
Search trajectory is sensitive to *when* restart policy is modified and how
strongly. Under otherwise identical Kissat source and exact same formula/CPU,
some policy switching schedules may improve formula-level time dramatically
and reversals or delayed switches may avoid harm. This is testable, not assumed.

### Arms / controls
* monitor: R6 instrumentation only; never switch restart policy
* r11_512_25: change restartint to 25 at 512 conflicts
* r11_1024_25: change restartint to 25 at 1024 conflicts
* r11_2048_25: change restartint to 25 at 2048 conflicts (R7 intervention)
* r11_4096_25: change restartint to 25 at 4096 conflicts
* r11_2048_50: change restartint to 50 at 2048 conflicts
* original_kissat: pinned uninstrumented Kissat reference
* stable_v1531: frozen and unchanged V15.3.1 reference

All five R11 arms plus monitor use one identical compiled patched Kissat and
its single live search; *no process restart*, no backtracking reset, no
allocation reset, no learned clause wipe. A switch is only the same native
restartint option update used in R7. The other two modes are practical
reference controls and are **not** same-binary causal interventions.

### Prospective test design
* 120 distinct generated 3-CNF (n=200/220/240, 40 per n,
  m=round(4.23*n)), with frozen new seeds and no outcome prescreen.
* 60 development plus **60 reserved test** cases, disjoint streams.
* 3 repeats each, 8 policies, 2880 individual executions; shuffled per
  formula and replicate; same pinned core within shard and one GitHub
  hosted runner for each 10-formula shard.
* Cap=12 seconds per run; timeout PAR-2=24 seconds. Report timeouts separately.
* Formula hash compared with frozen historical registry assembled from
  cumulative SQLite and earlier R10; registry must contain >1300 SHA-256.
* SAT assignments are validated against every CNF clause; direct Kissat
  UNSAT is not an independent proof certificate. Any disagreement or
  invalid SAT assignment invalidates the paired group.
* Record run, runner, executable hashes, pinned source, formula SHA-256,
  deterministic seed, CPU affinity, wall/cpu time, early counters, switch
  moment, before/after learned count, final conflicts and restart count.
* Dense passive checkpoints at 32,64,96,128,192,256,384,512,768,1024,
  1536,2048,3072,4096,6144,8192 conflicts. Prefix values at <=384
  (preintervention for every arm) must agree with monitor. Abort if not.

### Primary endpoints and decision protocol
1. Total PAR-2 and count solved in each arm, separately for development,
   reserved test, and each size stratum.
2. Per-formula 3-repeat paired ratios; gains >2x and regressions >2x;
   bootstrap 95% confidence interval by resampling **formulas** within
   size strata, not treating repeats as independent samples.
3. Scatter log2 gain versus preintervention propagations per conflict,
   structural degree CV/Gini and polarity imbalance; identify both
   extreme wins and extreme regressions.
4. Which timing arm is best is a **post-hoc exploratory result** on R11.
   Do not announce winner or general law from multiple comparisons.
   Any frozen timing-selection rule derived from this run requires a
   **different, later** independent follow-up holdout with unchanged rule.
5. Explicit negative controls: original monitor, original Kissat and
   the unchanged reference V15.3.1; distinguish overhead and
   computation changes.

Generated random 3-SAT is not an official SAT Competition test, and even
100-fold per-formula gains would not establish global solver speed or record.
The goal is to identify falsifiable early-dynamics / structural
relationships first, then test predictive selectivity on independent data.
