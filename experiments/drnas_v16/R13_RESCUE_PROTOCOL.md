# DRNAS SAT R13 — missed-win rescue / structure and early-dynamics audit

Preregistered on **2026-11-02** on branch `experiment/drnas-r13-rescue-gate-20261102`.

## Hypothesis and prior evidence

R12 verified 3,240 executions on 120 prospective random-3SAT formulas. Its
hybrid policy did **not** improve total held-out PAR-2. A forced change
of Kissat restart interval to 50 at 2048 conflicts gained 7.54% on R12
reserved generated formulas, but 95% formula-bootstrap interval included
regressions. Its very best example `r12_220_test_1_07.cnf` got 21.5x
on paired 3-trial totals; old hybrid abstained because at conflict 512
propagation/conflict ~45.29 and glue ratio ~1.024 fell outside the old
thresholds p<43 and g<0.95.

**Crucial:** R12 development AND formerly reserved R12 test formulas have
now been studied to generate this rule. They are no longer blind validation
of R13. The observed R12 retrospective 24-selected-instance +6.80% total
PAR-2 gain, 6 selected extreme >2x wins and 2 >2x regressions is
exploratory and selection-biased. Only new R13 seeds can validate.

## Frozen primary R13 rescue rule

Before solving: CNF variable count `n`. At first 512 conflicts in a
**single continuously running pinned Kissat process**, read
propagations/conflict `p` and fast/slow average LBD/glue ratio `g`.
If `n >= 220 && 0 < p < 46.5 && g >= 0.95` choose
restart interval 50 at conflict 2048. Otherwise leave Kissat unchanged.
Never restart the process, reset clauses, use SAT outcomes or learn from the
new holdout. The rule and SHA registry are committed before any R13 testing.

Comparators on the **same instrumented Kissat binary**:
- Monitor/passive instrumentation (primary causal baseline, no switch)
- Forced 2048/50, irrespective of early features
- Forced 2048/25, old intensity
- **R13 rescue50** (primary frozen rule)
- R13 rescue25, same selection with interval 25 (causal intensity ablation)
- R13 struct50, same gate plus `degree_cv >= 0.27` (structure ablation)
- R13 inverse50, `n >= 220 && 0 < p < 46.5 && g < 0.95` (negative control)
- Previously frozen R12 hybrid (conjunction of p<43, g<0.95, degree_cv>=0.265)
- Pinned original Kissat (different instrumentation, reference only)
- Untouched V15.3.1 Stable (different architecture, reference only)

## Prospective experiment

Generate exactly 120 new random-3SAT problems at 200/220/240 variables
(40 of each size), clause density 4.23, with deterministic seeds
`513130000+n*10000+(test?1000:0)+part*10+j`. Exactly 60 development
and 60 reserved test formulas, never cherry-picked. Freeze all 1654 prior
CNF SHA256 from cumulative historical identities through R12; reject
overlaps within or between shards. These are *new to our archived corpus*,
not guaranteed novel in all public formula collections and not official
SAT Competition formulas.

Each CNF: 10 strategies x 3 shuffled-order repeats = **3600 attempts**.
Use 12 independent Linux GitHub runners, one runner per shard of 10
formulas, pinned single logical CPU core for all strategies in a shard.
Cap=12 seconds, PAR-2 timeouts=24 seconds. Compare only **same CNF, same
shard, same runner**, never cross-runner raw timing.

Collect source SHA, Git commit, runner, CPU core, repeat, generator seed,
formula canonical bytes SHA-256, binary SHAs, telemetry for early
propagations/decisions/restarts/glue and conflict checkpoints, C-side
`R13_CHOICE`, actual `DRNAS_V177_SWITCH`, final conflicts, CPU and wall
seconds, witness/proof validation flags, and per-mode PAR-2.
Reject incorrect SAT witness, SAT/UNSAT contradictions or unauthorized
switches. Direct Kissat UNSAT needs independent certification before
strong correctness claims; report this limitation.

Compare prefix checkpoint values at <=384 conflicts against monitor
(same binary), reject mismatch. Do not count repeated timing trials as
independent formulas.

**Primary endpoint (test fold only):** percent change in total PAR-2 for
frozen R13 rescue50 vs monitor, with a 95% bootstrap confidence interval
resampling **entire formulas within each n stratum**. Report the
activation count, total time, 2x gains, 2x regressions and misses;
compare against R12 hybrid and all declared controls. If the interval
includes zero, claim only inconclusive evidence, not a breakthrough.
Preserve all 10-way paired raw artifacts and scatterplots.

Even if this experiment validates a modest effect in random-3SAT,
transfer to officially sourced and independently new SAT families with
certificates is required before general effectiveness or record claims.
The V15.3.1 solver, R11 and R12 research sources and existing
experimental branch results **must remain unchanged**.
