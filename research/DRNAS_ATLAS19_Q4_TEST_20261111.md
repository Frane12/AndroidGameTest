# DRNAS ATLAS19 — C7 adaptive against fixed-quarter deletion (2026-11-11)

Branch: `experiment/drnas-atlas19-q4-cadence-20261111`.
Based on frozen `experiment/drnas-atlas18-retention-factorial-20261111`.
Main and the completed ATLAS16/17/18 benchmark code are NOT changed.

## Preregistered question

ATLAS18 completed 100 SHA × 10 arms × 2 repeats with C7_ADAPT reported PAR2
237.52240 s, C6_KEEP 260.92036 s and best C8_GATE_Q8 249.76206 s.
In ATLAS18 C7 reports 298 high-pressure versus 10 low-pressure decisions.
Does the BCP-responsive decision improve results, or does merely keeping a
fixed 1/4 deletion quota at each 1500-conflict trigger explain it?

The safety rules/learned-clause protections and solver search are unchanged.
Controls C6_KEEP, C7_ADAPT and C7_ADAPT_GAUSS are generated from the same
frozen ATLAS17 parent, not altered by the C9 modes.

## Arms, exact intervention

- `C9_FIXED_Q4`: every 1500 conflicts, delete top 1/4 of ELIGIBLE poor,
  unlocked, long, high-LBD learned clauses; no BCP gate
- `C9_FIXED_Q4_GAUSS`: same with source-certified Gauss GF2
- `C9_SLOW_Q4`: every 3000 conflicts, same 1/4 quota (frequency control)
- `C9_SLOW_Q4_GAUSS`: same with source-certified GF2
- `C7_ADAPT` and `C7_ADAPT_GAUSS`: unchanged previous reference:
  at every 1500-conflict measurement, >8 watch visits per propagation
  triggers 1/4 deletion; low pressure waits for a 3000-conflict boundary
  and deletes 1/16
- Also `C6_KEEP`, `A`, pinned single-core `KISSAT` and `CMS`

The C9 branch does not activate C7 pressure logic; protected clauses remain
locked; compaction maintains reason/watcher IDs. It does not change CNF,
propagation semantics, SAT criteria or UNSAT proof claims.

## Frozen input and research honesty

SATLIB frozen original archives in ATLAS-wide were exhausted by past
cohorts (up through 99), so this run MUST distinguish:
- 75 genuinely FRESH synthetic SHA formulas: 15 generated families ×5,
  deterministic generator indices 100..104
- 25 `REPLAY_ATLAS18` original SATLIB SHA formulas: 5 archives ×5,
  earlier index 95..99. They are NOT unseen or a fresh blind holdout.

Per-source `novelty` is preserved in the append-only trial JSON and
manifest. The merge emits *separate PAR2 and solved counts* for FRESH and
REPLAY_ATLAS18 as well as the pooled score. Avoid claiming all 100 are blind.
A future source-disjoint real-original archive is essential before broad
claims or promoting changes.

100 source SHA × 10 arms × 2 reps = 2,000 matched E2E subprocesses.
Cap 8s, one logical CPU, 10 shards × 10 CNFs. Rotate solver order per
trial and freeze ATLAS15 policy before holdout. Use SHA-verified original CNF,
verified original SAT witness, independent reconstructed GF2 contradiction
proof, and never count uncertified UNSAT as verified PAR2 solved.
Audit BCP watch visits, propagations, deletions, compactions, resource use
and E2E times into an append-only SQLite record.

## Decision rules

Compare fixed Q4 to C7 on the same cases/seeds:
1. Strict verified PAR2, solved SAT and independently certified GF2 UNSAT,
2. Reported PAR2 (non-certified UNSAT is diagnostic only),
3. watch visits and absolute BCP work, not just ratio,
4. final source-family regression patterns and memory.
5. Do not assume fixed Q4 wins if only the synthetic cohort benefits.
If C9 improves on this exploratory mixed cohort, verify on a NEW independent
real original-CNF source cohort before changing the stable engine.
