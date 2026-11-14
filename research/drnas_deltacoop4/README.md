# DRNAS DELTA4 — generalized structural bridge on diverse medium-size original SAT

**Experiment only.** No edits to main, frozen DELTA3, competitors or original CNFs.

## Motivation and strict interpretation

DELTA3 successfully replayed a true affine-hull information-loss witness on one
original SAT2024 hardware-miter source and independently checked 2 one-step
global CNF RUP lemmas across 432 attempts. It did not improve solved count or
PAR2. Its rare affine countermodel witness was an excessively narrow activation
gate for general SAT formulas.

DELTA4 broadens when to look for original-source one-step resolvents.
It never asserts a proposed nonlinear/structural constraint directly.
Every emitted clause is an exact resolvent of two ORIGINAL clauses and is
independently checked against original parents. Only a proof-safe result may
reach CDCL; original assumptions and guards remain in the resolvent.

DELTA4 labels must be read narrowly:
- d4-struct: activation needs an exact cross-block join reduction and a
  nonaffine local truth table; this does NOT prove a new complexity theorem.
- d4: activation needs an exact join reduction, allowing both affine and
  nonaffine windows. It is general cross-block reasoning, not necessarily
  nonlinear-specific information.
- d4-shadow: same generalized scan; never injects.
- bridge: frozen DELTA3, activated only by its original nonlinear tuple witness.
- off, KISSAT, CADICAL: frozen references.

The split between d4-struct, d4, and shadow measures whether relaxing the
gate creates useful clauses or just extra computational overhead.

## General formula handling

A deterministic bounded 12,000-clause reservoir replaces DELTA3's policy of
disabling the entire module as soon as 12,000 original clauses are ingested.
An enlarged 1,000,000-variable eligibility cap permits examination of more
real formulas. Selected windows always contain exact, unmodified original
clauses. SHA-pinned original inputs and DRAT proof checking remain mandatory.

All CDCL experiments retain original algebra budgets (max 30ms total, 24
passes, 2.5ms/pass), an 8-lemma pass bound and at most 256 clauses total.
Each individual source is solved by each arm on one logical CPU.

## Original SAT2024 cohort

The official SAT Competition 2024 main archive is accessed via ZIP range reads.
Choose **60** original CNFs with unique normalized filename families,
compressed-size-stratified from 40k-900k byte entries, with deterministic
fallback tiers. Preserve original SHA, nvars, nclauses and archive filename.
Avoid 36 previously used REAL36 source SHA.

**Important:** file size is a scale proxy, not a measured hardness guarantee.
We report verified runtime-based medium difficulty descriptively after the
entire unconditional primary cohort. The primary comparison may not condition
on measured runtimes or expected outcomes.

Benchmark: 60 sources x 2 repetitions x 7 arms = **840 paired attempts**.
Exactly **10 seconds per solver attempt**, one CPU, 12 shards, 5 sources/shard.
SAT outputs are checked against original clauses and UNSAT is counted only
with a checked original-source DRAT proof. All new bridge events independently
validate original parents, exact pivot and RUP. Bootstrap confidence intervals
resample by source/family, not individual repetitions.

This is a retrospective development evaluation of known SAT2024 public
instances, **not** a sealed new blind holdout and never sufficient for model
promotion. If a policy succeeds here, verify its frozen parameters on a fresh
source-disjoint family-separated holdout and demand at least 10% verified
PAR2 improvement with a positive uncertainty margin and zero invalid answers.
