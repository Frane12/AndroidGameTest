# DRNAS X4.7 LONG — larger, longer, certificate-aware comparison

Branch: experiment/drnas-x47-longer-120-20261113
Workflow: .github/workflows/drnas-x47-long.yml

## Test intent

The previous X47 small-instance experiments had 112 distinct original synthetic
CNF sources, most solving in only a few milliseconds. X46 short search clones
saved some future conflicts but spent more time cloning/probing than they saved.
This new experiment lengthens BOTH the difficulty of input formulas and the
per-solver time budget, to determine whether short probing pays for itself on
more meaningful searches. It is not assumed to produce a speedup.

## Scope and resources

- 96 SHA-distinct synthetic original CNFs, 6 mathematically different
  generators with 16 sources each; four source-disjoint shards (24 each).
  ~100–180 variables on random/structured planted formulas, plus strictly
  encoded structural pigeonhole UNSAT controls and a 3-coloring SAT generator.
- 24 original retrospective SAT Competition 2024 CNFs selected without
  looking at solver outcome or benchmark speed. One normalized source-name
  family per original. Zip archive entry path and original CNF SHA256
  retained in the manifest.
- Five serial solver choices: CORE; X46_8; X46_128; X46_LEARNED_8; and
  X47_RISKGATE_8. One fourth-decision checkpoint per solve. Models are
  trained/frozen on a separate 84-source synthetic cohort (63 training,
  21 validation) before the 120 test sources are processed.
- Two repeats per original source per arm; 6s cap for synthetic, 8s for
  retrospective official. Up to 1,200 scored solver trials, parallel
  source-level shards, single CPU in each shard and rotated arm order.
- The experimental parent search never imports learned clauses or search
  state from its two bounded probe copies. Branch polarity alone can change
  after a completed probing decision. Restart schedules retained.
- SAT results only credited after independently checking the emitted witness
  against the ORIGINAL CNF.
- Synthetically constructed strict pigeonhole (p>h) UNSAT is independently
  certified by matching the complete pigeon-at-least-one and
  hole-at-most-one source-clause core. The pigeonhole theorem guarantees
  the conjunction is contradictory. This is a special structural
  certificate, **not** general DRAT/LRAT verification.
- Official UNSAT results have NO general independent certificate here.
  They are marked UNSAT_UNVERIFIED and earn PAR2=2*cap, not solved credit.
- Unverified/UNKNOWN/TIMEOUT also earns PAR2=2*cap. Solved time is the
  end-to-end elapsed subprocess + SAT witness check if <=cap. Recorded
  probe time includes both internal clones, is already part of elapsed
  time, and is shown separately for analysis (not double counted).
- Repeats are NOT independent test formulas; 120 SHA-distinct original
  CNFs are the potential independent units, and family-level results must
  be reviewed separately. Formula-bootstrap CI is conditional on this mix.
- SAT Competition 2024 sources have appeared in many prior research
  experiments. These are original external problems, but the retrospective
  cohort is **not globally blind**.

## Criteria and interpretation

Report verified PAR2, SAT/UNSAT independently verified counts, unresolved/
UNSAT-unverified counts, native decisions and conflicts, triggered probes,
probe skips, active flips and total probe wall time for EACH solver and
cohort. Include a family grouping and a cluster bootstrap confidence
interval for paired PAR2 differences with original CNF SHA as the
independent unit. Record all source SHA and fixed policy SHA.

A *positive* speed claim requires an independently certified, paired
end-to-end PAR2 improvement that is not offset by fewer verified solved
problems; a single synthetic-source win is not a general solver advantage.

Because these are larger formulas, it is possible (and scientifically
informative) for all tested arms to hit the time cap. That would give
no evidence of superior speed and would require a more suitable hardness
curriculum, not an invented speedup.

## Reproduce

Training:
  python3 research/drnas_x46_probe_bench.py --binary build/drnas-x47 \
    --out train --per-family 12 --repeats 2 --cap 0.8 \
    --index-offset 600000 --probe-ms 1.5
  python3 research/drnas_x46_cost_train.py \
    --trials train/trials.jsonl --model train/frozen_cost_model.txt \
    --report train/cost_report.json
  python3 research/drnas_x47_guard_fit.py \
    --trials train/trials.jsonl \
    --frozen-cost-model train/frozen_cost_model.json \
    --guard-output train/frozen_risk_guard.txt \
    --report train/guard_report.json

The long test itself is split between GitHub Action matrix shards for
synthetics and a separate independent official retrospective job.
Aggregate source-level results with research/drnas_x47_long_aggregate.py.

Do not promote experimental X4.7 to the default/main branch without a
verified statistically meaningful real performance advantage.
