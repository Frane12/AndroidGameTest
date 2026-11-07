# DRNAS SAT — verified status and WorldSim W1 selection, 2026-11-07

Selection is frozen before consulting outcomes of the running TA3-2026 or TA4 experiment. TA3 is the primary candidate; unchanged R28+Kissat is a second candidate. No candidate is selected retrospectively on the WorldSim evaluation set.

## Completed source-paired experiments

| Experiment | Candidate | Candidate PAR-2 total, s | Baseline | Baseline PAR-2 total, s | Baseline/candidate ratio | Solved attempts |
|---|---|---:|---|---:|---:|---|
| TA3 SAT2025, 24 originals, 2 reps | TA3 portfolio | 1451.750154 | Kissat 4.0.4 | 1575.969530 | 1.085565× | 14/48 vs 10/48 |
| TA3 SAT2025 | TA3 portfolio | 1451.750154 | CryptoMiniSat 5.11.15 | 1589.570685 | 1.094934× | 14/48 vs 10/48 |
| R199 SAT2025, 40 originals, 3 reps | R28+Kissat | 3440.828233 | Kissat 4.0.4 | 3560.914758 | 1.034900× | 36/120 vs 33/120 |
| R199 SAT2025 | R28+Kissat | 3440.828233 | CryptoMiniSat 5.11.15 | 3684.655586 | 1.070863× | 36/120 vs 30/120 |
| TD2 development, exposed R199 sources, 2 reps | Kissat sparse budget | 2304.872815 | Kissat | 2360.573490 | 1.024167× | 24/80 vs 23/80 |

PAR-2 charges each timeout twice the 20-second attempt cap. A PAR-2 ratio is a penalized-score ratio, not literal CPU acceleration for every solved formula. Rows are separate experiments and must not be pooled as one benchmark. Solved counts above count repeated attempts, not distinct formulas.

TA3 source-cluster bootstrap, 10,000 resamples of 24 formulas, seed 20261107: ratio 95% interval 0.9791–1.2648 versus Kissat and 0.9992–1.2778 versus CMS. Both include equality. This is a promising prospective result on this sample, not a demonstrated general SAT advantage. Generic CDCL UNSAT has not been independently LRAT checked.

## Actual-time examples from TA3

| Source | TA3 median wall seconds | Reference median wall seconds | Interpretation |
|---|---:|---:|---|
| 4c3001f8-fixed-shape-random | 4.284159 | Kissat timeout at 20 | At least 4.67× versus capped Kissat; TA3 selects CMS, whose time is similar |
| 82851650-reg-n | 0.9621725 | CMS timeout at 20 | At least 20.78× versus capped CMS; TA3 selects Kissat, whose time is similar |
| d07b7175-purdom-instances | 8.733043 | Kissat 15.402721 | 1.76× measured; TA3 selects CMS |

These show portfolio complementarity. They are not claims that a new internal solving engine outperforms the selected backend.

TK mixed generated controls, 12 formulas × 3 reps: clean 1.575181s, active lazy cooldown 1.740688s. All solve 36/36, but active is slower and produces zero XOR reasons/proposals. It is not promoted to W1.

## Sources checked directly

- [TA3 final audit](https://github.com/Frane12/AndroidGameTest/actions/runs/42393279231/job/128469467086), plus all eight raw shard logs, 384 trials.
- [R199 final audit](https://github.com/Frane12/AndroidGameTest/actions/runs/42390697619/job/128465181546), 720 trials.
- [TD2 final audit](https://github.com/Frane12/AndroidGameTest/actions/runs/42393873346/job/128473945658), 640 development trials.
- [TK final audit](https://github.com/Frane12/AndroidGameTest/actions/runs/42391271033/job/128459283441), 108 generated trials.
- Running when selected: [TA4](https://github.com/Frane12/AndroidGameTest/actions/runs/42395771235) and [TA3 SAT2026](https://github.com/Frane12/AndroidGameTest/actions/runs/42396350093). No completed timing claim is made for them here.

## WorldSim W1 preregistration

- All 24 original CNFs from the already frozen TA3-2026 artifact, run 42396350093, are included. No formula is selected by observed speed or outcome. This is a repeated frozen evaluation cohort, not a newly globally blind sample.
- Six arms: unchanged TA3 source portfolio, unchanged R28+Kissat, native Kissat 4.0.4, CryptoMiniSat 5.11.15 single thread, CaDiCaL 3.0.1, and the official SAT2026 satsuma-iter+kissat entrant from its checksum-verified submitted archive. No champion title is inferred from older DRNAS workflows or inconsistent summary pages.
- 3 repetitions, 60-second wall cap including per-formula profiling/selection/solver launch; 432 attempts total; 8 disjoint shards of 54 attempts. Within a shard, all arms are sequential, deterministic shuffled order, inherited single-CPU affinity. All run the same original source bytes.
- SAT models checked on the original CNF after timing for every arm. Every CDCL backend requests proof output, including R28 fallback wrappers and the submitted entrant. Proof bytes and standard proof presence are recorded. R28's algebraic fast path may lack a standard proof file. Generic UNSAT is consistency-checked across solvers/repetitions; independent submitted proof verification is absent.
- Fail closed on hash drift, wrong verdict/model, contradictory answers, duplicate or incomplete pairs. No partial shard can produce a final ranking.
- Report PAR-2 totals, wall totals, solved attempts and unique formulas, and source-cluster bootstrap uncertainty. All timeouts remain in the score. Preserve code/source/binary pins, commands, raw stdout and machine metadata.
- The official sequential competition uses a 5000-second limit and a larger full competition set. W1 is a reduced-budget unofficial comparison and cannot establish an official ranking or world record.

Official references: https://satcompetition.github.io/2026/nhr.html and https://satcompetition.github.io/2026/rules.html.
