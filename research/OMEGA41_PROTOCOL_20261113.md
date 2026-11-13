# DRNAS MATH Ω4.1 — source-certified online GF(2) causal utility experiment
Date: 2026-11-13. Status: development-only, **no speedup claim until aggregation**.

This is **not** an independent SAT solver: all solve modes invoke a *single compiled*
CaDiCaL 2.1.0 binary via IPASIR-UP. Original source CNFs from the historical
XORABC2 archive are immutable and SHA-256 verified.

## Hypothesis

If fewer Gauss–Jordan recomputations are performed when mathematically correct
GF(2) implications yield almost no *accepted reasons*, the solver's end-to-end
work may decrease without modifying correctness. An omitted deduction cannot
make a false claim; the original CaDiCaL still handles the whole CNF.

## Four matched modes

- `clean`: CaDiCaL without external propagator.
- `shadow`: source-certified extraction and full online scan but no external
  clauses or propagations; isolates instrumentation overhead.
- `live`: full Ω4 online elimination and certified CNF reasons.
- `gated`: same live engine, but scans all of the first 128 distinct trail
  states and thereafter samples 1/8 of new states when
  `(completed_reasons+conflict_clauses)*64 < scans`. Its scan cap is 6000 vs
  12000 for full live. Thresholds are fixed *before* comparing any Ω4.1 scores.

## Evidence and safety

- Exactly 16 historically exposed original formulas: 8 complete source-XOR
  positive and 8 no-exact-XOR controls, selected only from frozen source
  signatures; plus 4 synthetic, oracle-verified controls.
- 2 repetitions, 5.0 seconds per solver arm *including source extraction*,
  one logical CPU per solver. Arm order deterministically permuted by source SHA
  and repetition. No training, no holdout claim.
- Every new GF(2) reason includes full source-row ancestry. The bridge
  reconstructs the original full row independently of live elimination, checks
  its residual against the active CDCL trail, and only then emits reasons.
  Inconsistency fails closed. SAT witnesses are checked on the original CNF.
- Record reported vs independently certified PAR-2 separately. Backend UNSAT
  without an independently checked original-CNF proof is **not certified**.
  No claimed solver conflicts/decisions if CaDiCaL stats are missing.
- Telemetry separates candidate units, external unit proposals, accepted reason
  clauses, clauses emitted as conflicts, source row combinations, scan walltime,
  reason width and proof ancestry depth. Candidate counts are not speedups.
- Failure to reduce PAR-2 or true CDCL work is a negative research result.
  A prospective blind SHA- and family-disjoint holdout with Kissat, CaDiCaL and
  CryptoMiniSat is required before any promotion to a champion.

## Pinned source

- Live bridge: `research/omega4_live_gf2.cpp`
- Runner: `research/omega41_benchmark.py`
- Source-only independent extractor: `research/drnas_xorabc3_source_rows.cpp`
- Workflow: `.github/workflows/drnas-math-omega41.yml`
- Reuses frozen development cases from archived GitHub run 42809444478
- CaDiCaL source commit: `31f9aae44947c673dc6190c9beb399acb9ffec6a`

All changes on `experiment/drnas-math-omega41-20261113`; `main` untouched.
Inherited APK-on-push job is limited to `main` in this research branch.
