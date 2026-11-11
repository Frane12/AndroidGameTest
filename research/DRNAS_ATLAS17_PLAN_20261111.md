# DRNAS ATLAS17 — BCP-pressure-adaptive retention, proof-first blind experiment

Date: 2026-11-11. Base: `experiment/drnas-atlas16-mega-keep-20261111`. 
This experiment changes **only an experimental branch**, not main or ATLAS16 controls.

## Motivation from completed ATLAS16 (18,000 oneCPU trials)
- C5_CDCL reported PAR2: 5,109.22 s; C6_KEEP: 4,875.45 s (1.048x improvement).
- C6 removed 59.09% fewer learned clauses than C5 across three stages.
- C6_KEEP_GAUSS independently verified 150 source-entailed GF(2) UNSAT cases.
- KISSAT 521.56 s reported PAR2 vs C6 4,875.45 s. The gap remains significant.
- **Important:** non-GF2 solver UNSAT responses lack independently verified LRAT
  and count as unsolved in verified PAR2. Stage 3 replay of stage 2 was nonblind.

## Hypothesis and frozen intervention
BCP watches can become expensive when weak learned clauses accumulate.
C7_ADAPT starts with *exactly* C6_KEEP's CDCL correctness and proof rules.
At 1,500-conflict intervals, measure the **delta watch visits per delta propagated
literal**. This is a lightweight workload proxy, not CPU timing.
- High pressure: ratio >8:1. Delete top **1/4** eligible weak learned clauses.
- Low pressure: evaluate only at 3,000-conflict multiples and delete **1/16**.
- Control C6 still deletes **1/8** at each 1,500-conflict interval.
- Preserve all locked reasons, LBD <7, and short clauses. Retain safe remapping
  of reasons, watches and learned LBD when compacting.
- This is a selection and memory-management experiment only, never an
  unverified assignment/implication or an unsafe UNSAT rule.

## Frozen comparison
- 200 fresh CNF SHA values, 20 categories x 10 each; indices 85–94 of
  the pinned deterministic generator and SATLIB archives, no source overlap
  with ATLAS16 indices 35–84.
- 50 original SATLIB archive formulas, 150 generated controls.
- 8 matched solver arms, 2 independent rep/seed values: 3,200 attempts.
- Arms: A, C5_CDCL, C6_KEEP, C6_KEEP_GAUSS,
  **C7_ADAPT**, **C7_ADAPT_GAUSS**, KISSAT, CMS.
- One logical CPU per subprocess and single-thread CMS; 8-second wall cap.
- Build and smoke then 8 shards (25 CNFs each), merge with SHA audit.
- SQL journal stores every trial with measured decisions, conflicts,
  BCP propagations, watch visits, GF2 checks, pressure/low cycles, deletes,
  compactions and independently verified original-CNF SAT/GF2 UNSAT.
- The GAUSS arm uses only complete original-CNF parity encodings with a
  source-reconstructable GF2 contradiction; unverified UNSAT is *not* credited.
- Matched, reported and strictly verified PAR2 are always reported separately.
- **No** policy changes based on these holdout results before the experiment
  completes, and no cross-run online learning claim.

## Interpretation rule
An improvement over C6 requires at least: lower matched reported PAR2,
no loss in verified SAT/GF2-UNSAT coverage, and fewer BCP watch visits per
propagation in relevant hard categories. If C7 worsens results, retain C6,
do not silently promote C7 to main. Check cross-solver disagreements as a
hard failure and inspect individual original source SHA outliers.
