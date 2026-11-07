# DRNAS New Horizon SAT R3 — early abstention and system integrity

## Scientific idea
The user-defined SAT system and its source CNF remain immutable. Only the
decision model may be approximate. Instead of guessing that an unknown SAT
formula is "mixed", the cheap observer looks for **negative certificates**
that a source **cannot** belong to a tractable class. A single original clause
can soundly reject source-wide Horn-SAT, 2-SAT, or pure XOR3.

R3 refines R2; it does NOT claim a new polynomial algorithm for general SAT.

## Source-only fast gate
1. Limit source analysis by original DIMACS file size / clause metadata.
2. Observe up to 64 complete original clauses, **stopping immediately** if:
   - one clause contains more than one distinct positive literal (not Horn);
   - one clause has over two distinct literals (not 2-SAT);
   - the source is not fully observed as a 3-literal parity encoding.
3. A positive candidate is not proof; before using a special algorithm the
   ENTIRE original CNF must be parsed and verified.
4. If proven Horn, use exact forward chaining; if proven 2-SAT use SCC;
   if proven source-exact XOR3 use R164 GF(2).
5. Otherwise fall back to the unmodified pinned CaDiCaL 2.1 binary.
6. All detection, verification, solver execution and timeouts are included
   in trial wall-clock timing.

## What "robust linearization" means
R2's conservative affine cost estimator is reused. It estimates potential
runtime advantage but does not change clauses or semantic behavior.
The early-abstention gate is a linear-time bounded scan, not full mathematical
linearization of arbitrary SAT. An early **rejection** is deductively safe;
an early **acceptance** is only hypothetical and requires complete proof.

## Tests
- Existing R2 exhaustive random Horn/2SAT tests and R3 negative-certificate
  tests including deceptive 96-clause prefixes.
- Renaming and reordering invariance for structural recognition.
- 114 SHA-identical frozen R2 formulas, including reused real originals.
- 12 new deterministic Horn examples and 12 new deterministic 2SAT examples
  using previously known generators with different seeds.
- 8 new deterministic planted-SAT unknown-control formulas.
- 146 source formulas, two repetitions, four methods = **1168 paired runs**.
- All arms use exactly the same pinned CaDiCaL binary SHA from R2.
- Policies: clean, early-probe shadow, R2, R3.
- Aggregate audit: source SHA / same-arm pairing / SAT witness verification /
  no contradictory SAT/UNSAT / PAR2 + per-cohort runtime.

## Scientific caveats
- Reused real CNFs and new samples from known generators are **not** a blind
  external industrial holdout. New synthetics have known planted/structural
  answers.
- Native UNSAT results lack independent LRAT proof; source-equivalent
  GF2 contradiction and exact Horn/2SAT algorithms have algorithmic
  mathematical justification but no LRAT artifact in R3.
- Tiny sub-millisecond benchmark time differences may be runner noise.
- General SAT complexity is unchanged.
- Return only current-run measured speedups; never infer them before audit.

## Reproducibility
- Workflow: .github/workflows/drnas-new-horizon-sat-r3.yml
- Files: research/new_horizon_r3.py, research/new_horizon_r3_benchmark.py
- R2 frozen input run: 42322926260; SHA-256
  f2ced9794fbea5ab9420e6f7db0e43106e35c85a28a70cf5893cf7cc20ec19b7
- Native SHA-256:
  d3e17f52ee77be0df090da28710a10ba9543576e8ca12e9b2555288a02a077ed

## Question for the next phase
Should R4 prioritize early dynamic information on structures which cannot
be classified in the first source scan, or expand exact structural motif
coverage while strictly measuring CPU overhead?
