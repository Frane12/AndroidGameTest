# ATLAS38 — One-reduction causal deletion study
2026-11-11; experimental branch only.

## Question
Does deleting 100% rather than 75% of C7's eligible deletion quota
at **one selected reduction** cause subsequent CDCL work to increase,
when all earlier work is identical?

## Experimental design
- Isolated native C++ from ATLAS37, with default A36_75 frozen.
- SATLIB source SHA frozen: `uf250-1065` indices 10/11 and
  `uuf250-1065` index 11; original canonical CNF, 2 seeds.
- At each target eligible reduction number 5, 15, 30, 45, pair
  `A38_PULSE75_N` against `A38_PULSE100_N`.
- **Before** target both run fixed 75% deletion, same SHA and seed.
  At target, only deletion quota differs (75 vs 100). Every later
  reduction returns to fixed 75%.
- Pre-intervention fingerprint mixes CDCL decisions, conflicts,
  propagations, watch visits, deleted clauses, live clause count and
  trail assignments. Must match along with explicit printed counters.
- This is deterministic **replay** from initial state, not a bitwise
  deep copy or same-process fork. Fingerprint equality is a useful
  invariant, not absolute proof of every internal field's equality.
  One-Cpu per individual process, no race between paired runs.
- Time cap 12s; timeout output in stderr is recovered so the
  intervention marker is not silently lost when child is killed.
- Control A36_75 plus pinned Kissat for context; SAT verified on
  original CNF, UNSAT without independent LRAT flagged unverified.
- 3 SHA × 2 seeds × (8 interventions + 2 controls) = 60 trials.
  24 paired interventions. Do not pool multiple target checkpoints as
  independent source samples or claim a globally blind holdout.

## Important interpretation
- Within-source delta in E2E / conflict count can suggest causal
  effects of the *specific pulse* under deterministic replay, provided
  pre-state fingerprints match.
- Do not use same-source replay results to tune a policy and then claim
  unbiased generalization on that source.
- High watch/prop ratio alone does not justify aggressive deletion.
- Clauses discarded in one branch cannot be said to be 'relearned'
  without logging learned-clause canonical hashes; this experiment
  does not measure identical-clause relearning.
- Benchmark should declare reductions whose target was not reached
  as uninformative, not a null effect.
- Memory and CPU timing results on shared CI hosts are noisy; number
  of conflicts, decisions and propagations are more reproducible.

## Source
- Generator: `research/drnas_atlas38_build.py`
- Matched benchmark: `research/drnas_atlas38_benchmark.py`
- Audit: `research/drnas_atlas38_audit.py`
- Workflow: `.github/workflows/drnas-atlas38-single-pulse.yml`.
