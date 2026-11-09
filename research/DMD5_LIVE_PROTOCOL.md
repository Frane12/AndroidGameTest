# DRNAS DMD5-LIVE — Conditional progress with measured real CDCL trail
Preregistered 2026-11-09, frozen experimental branch
`experiment/drnas-dmd5-live-conditional-holdout-20261109`.

## Hypothesis
DMD3X-C's offline deterministic conditional-UP score predicts some but
not all real CaDiCaL lemma unit events. When locally proved lemmas are
injected, the actual solved outcome and total E2E may improve, but
instrumentation plus solver search reordering may be expensive.

## Sources and controlled comparison
- 24 SHA-sorted original official EQUIV7 CNFs *after* the first 24
  sources used to develop DMD3X-C, plus 4 independently generated small
  proof-soundness controls.
- These 24 are disjoint from DMD3X-C's previous 24 original formulas,
  but are **not** fresh across all DRNAS/SAT project experiments. No
  broad blind competition or claim of global superiority.
- 8 one-core sequential solver variations per original, two repeats,
  eight-second full E2E timeout, 4 independent CI shards:
  **448 attempts**, 112 per shard.
- Primary baseline: original pinned Kissat 4.0.4. Secondary baseline:
  clean pinned CaDiCaL 2.1.0. Exact candidate-matched CaDiCaL
  observer-only placebo, `dmd5_8_active`/`dmd5_8_shadow`,
  `dmd5_16_active`/`dmd5_16_shadow`, and
  `dmd5_all_active` as the eighth arm.

## Algorithm
1. Verify original SHA and parse the full CNF. Source-only early
   abstention when file size exceeds 12 MB or >125000 clauses.
2. Run unchanged native DMD3X 60ms in all mode (up to 24 lemmas),
   with independent exhaustive original-local clause-source replay.
3. Run unchanged DMD3X-C native conditional-UP filter (250ms soft
   deadline), producing the ranked subset of at most 16 clauses.
   A budget expiration or no positive direction means no clauses
   are added, while any prep cost still counts toward full E2E.
4. For the 8-clause dose, take the first 8 deterministic chosen clauses
   and independently replay only their original-source proof again.
5. Active vs shadow use EXACTLY matched selected CNF SHA fingerprints;
   active adds proof-checked lemmas to CaDiCaL, shadow observes identical
   variables/clauses but solves only the original CNF.
6. DMD5 native CaDiCaL ExternalPropagator on actual assignment and
   backtracking callbacks records per-lemma unit opportunities,
   falsifications, first-unit assignment count/depth/time, and a
   classical CaDiCaL decisions/conflicts/propagations audit. The
   ExternalPropagator does not assert new clauses or propagation;
   every active clause is added only before solving.
7. An observer-only placebo (same preprocessor, same candidate
   monitored-variable set but no clause evaluation) isolates the
   callback performance overhead.
8. Strict audit counts only SAME original SHA/repetition/lemma
   candidate signatures for active versus shadow; comparisons of
   CDCL decisions/conflicts require the same solved verdict and both
   statistics present; timeout-vs-timeout is **not** causal evidence.

## Scientific safeguards
- One logical CPU pinned per native process, no two-core portfolios
  in main comparison.
- Full end-to-end timer includes preprocessing, proof replay, Python
  overhead, candidate selection, observer callbacks and solver.
- SAT assignment must satisfy original CNF in C++ and independently
  in Python. UNSAT from solver remains backend-only status until an
  independent LRAT proof is checked.
- Per-lemma events are *observational* and do NOT prove avoided
  conflicts or a new unit implication not already performed by
  internal CDCL.
- Report PAR2 sums, solved, SAT verified, backend UNSAT, regression
  spectrum, decision/conflict counts among comparable pairs, and
  per-shard/case activation notes. No automatic promotion to main.
